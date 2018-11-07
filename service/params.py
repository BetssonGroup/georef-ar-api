"""Módulo 'params' de georef-ar-api

Contiene clases utilizadas para leer y validar parámetros recibidos en requests
HTTP.
"""

import re
from enum import Enum, unique
from collections import defaultdict
from flask import current_app
import service.names as N
from service import strings, constants

MAX_RESULT_LEN = current_app.config['MAX_RESULT_LEN']
MAX_RESULT_WINDOW = current_app.config['MAX_RESULT_WINDOW']


class ParameterParsingException(Exception):
    """Excepción lanzada al finalizar la recolección de errores para todos los
    parámetros.

    """

    def __init__(self, errors):
        self._errors = errors
        super().__init__()

    @property
    def errors(self):
        return self._errors


class ParameterValueError(Exception):
    """Excepción lanzada durante el parseo de valores de parámetros. Puede
    incluir un objeto conteniendo información de ayuda para el usuario.

    """

    def __init__(self, message, help):
        self._message = message
        self._help = help
        super().__init__()

    @property
    def message(self):
        return self._message

    @property
    def help(self):
        return self._help


class ParameterRequiredException(Exception):
    """Excepción lanzada cuando se detecta la ausencia de un parámetro
    requerido.

    """

    pass


class InvalidChoiceException(Exception):
    """Excepción lanzada cuando un parámetro no tiene como valor uno de los
    valores permitidos.

    """

    pass


@unique
class ParamErrorType(Enum):
    """Códigos de error para cada tipo de error de parámetro.

    Nota: En caso de agregar un nuevo error, no reemplazar un valor existente,
    crear uno nuevo.

    """

    UNKNOWN_PARAM = 1000
    VALUE_ERROR = 1001
    INVALID_CHOICE = 1002
    PARAM_REQUIRED = 1003
    INVALID_BULK = 1004
    INVALID_LOCATION = 1005
    REPEATED = 1006
    INVALID_BULK_ENTRY = 1007
    INVALID_BULK_LEN = 1008
    INVALID_SET = 1009


class ParamError:
    """La clase ParamError representa toda la información conocida sobre un
    error de parámetro.

    """

    def __init__(self, error_type, message, source, help=None):
        self._error_type = error_type
        self._message = message
        self._source = source
        self._help = help

    @property
    def error_type(self):
        return self._error_type

    @property
    def message(self):
        return self._message

    @property
    def source(self):
        return self._source

    @property
    def help(self):
        return self._help


class Parameter:
    """Representa un parámetro cuyo valor es recibido a través de una request
    HTTP.

    La clase se encarga de validar el valor recibido vía HTTP (en forma de
    string), y retornar su valor convertido. Por ejemplo, el parámetro
    IntParameter podría recibir el valor '100' (str) y retornar 100 (int).
    La clase Parameter también se encarga de validar que los parámetros
    requeridos hayan sido envíados en la petición HTTP.

    La clase Parameter y todos sus derivadas deben definir su estado interno
    exclusivamente en el método __init__. Los métodos de validación/conversión
    'get_value', 'validate_values', etc. *no* deben modificar el estado interno
    de sus instancias. En otras palabras, la clase Parameter y sus derivadas
    deberían ser consideradas inmutables. Esto facilita el desarrollo de
    Parameter ya que el comportamiento sus métodos internos solo depende de un
    estado inicial estático.

    Attributes:
        _choices (list): Lista de valores permitidos (o None si se permite
            cualquier valor).
        _required (bool): Verdadero si el parámetro es requerido.
        _default: Valor que debería tomar el parámetro en caso de no haber sido
            recibido.

    """

    def __init__(self, required=False, default=None, choices=None):
        """Inicializa un objeto Parameter.

        Args:
            choices (list): Lista de valores permitidos (o None si se permite
                cualquier valor).
            required (bool): Verdadero si el parámetro es requerido.
            default: Valor que debería tomar el parámetro en caso de no haber
                sido recibido.

        """
        if required and default is not None:
            raise ValueError(strings.OBLIGATORY_NO_DEFAULT)

        self._choices = choices
        self._required = required
        self._default = default

        if choices and \
           default is not None:
            try:
                self._check_value_in_choices(default)
            except InvalidChoiceException:
                raise ValueError(strings.DEFAULT_INVALID_CHOICE)

    def get_value(self, val):
        """Toma un valor 'val' recibido desde una request HTTP, y devuelve el
        verdadero valor (con tipo apropiado) resultante de acuerdo a las
        propiedades del objeto Parameter.

        Args:
            val (str): String recibido desde la request HTTP, o None si no se
                recibió un valor.
            from_source (str): Ubicación de la request HTTP donde se recibió el
                valor.

        Returns:
            El valor del parámetro resultante, cuyo tipo depende de las reglas
            definidas por el objeto Parameter y sus subclases.

        """
        if val is None:
            if self._required:
                raise ParameterRequiredException()
            else:
                return self._default

        parsed = self._parse_value(val)

        if self._choices:
            self._check_value_in_choices(parsed)

        return parsed

    def validate_values(self, vals):
        """Comprueba que una serie de valores (ya con los tipos apropiados)
        sean válidos como conjunto. Este método se utiliza durante el parseo
        del body en requests POST, para validar uno o más valores como
        conjunto. Por ejemplo, el parámetro 'max' establece que la suma de
        todos los parámetros max recibidos no pueden estar por debajo o por
        encima de ciertos valores.

        Args:
            vals (list): Lista de valores a validar en conjunto.

        Raises:
            ValueError: Si la validación no fue exitosa.

        """
        # Por default, un parámetro no realiza validaciones a nivel conjunto
        # de valores.
        pass

    def _check_value_in_choices(self, val):
        """Comprueba que un valor esté dentro de los valores permitidos del
        objeto Parameter. El valor ya debería estar parseado y tener el tipo
        apropiado.

        Args:
            val: Valor a comprobar si está contenido dentro de los valores
                permitidos.

        Raises:
            InvalidChoiceException: si el valor no está contenido dentro de los
                valores permitidos.

        """
        if val not in self._choices:
            raise InvalidChoiceException(strings.INVALID_CHOICE)

    def _parse_value(self, val):
        """Parsea un valor de tipo string y devuelve el resultado con el tipo
        apropiado.

        Args:
            val (str): Valor a parsear.

        Returns:
            El valor parseado.

        Raises:
            ValueError, ParameterValueError: si el valor recibido no pudo ser
                interpretado como un valor válido por el parámetro.

        """
        raise NotImplementedError()

    @property
    def choices(self):
        return sorted(list(self._choices))


class StrParameter(Parameter):
    """Representa un parámetro de tipo string no vacío.

    Se heredan las propiedades y métodos de la clase Parameter, definiendo
    nuevamente el método '_parse_value' para implementar lógica de parseo y
    validación propias de StrParameter.

    """

    def _parse_value(self, val):
        if not val:
            raise ValueError(strings.STRING_EMPTY)

        return val


class IdParameter(Parameter):
    """Representa un parámetro de tipo ID numérico.

    Se heredan las propiedades y métodos de la clase Parameter, definiendo
    nuevamente el método '_parse_value' para implementar lógica de parseo y
    validación propias de IdParameter.

    """

    def __init__(self, length, padding_char='0', padding_length=1):
        self._length = length
        self._padding_char = padding_char
        self._min_length = length - padding_length
        super().__init__()

    def _parse_value(self, val):
        if not val.isdigit() or \
           len(val) > self._length or \
           len(val) < self._min_length:
            raise ValueError(strings.ID_PARAM_INVALID.format(self._length))

        return val.rjust(self._length, self._padding_char)


class StrOrIdParameter(Parameter):
    """Representa un parámetro de tipo string no vacío, o un ID numérico.

    Se heredan las propiedades y métodos de la clase Parameter, definiendo
    nuevamente el método '_parse_value' para implementar lógica de parseo y
    validación propias de StrOrIdParameter.

    """

    def __init__(self, id_length, id_padding_char='0'):
        self._id_param = IdParameter(id_length, id_padding_char)
        self._str_param = StrParameter()
        super().__init__()

    def _parse_value(self, val):
        if val.isdigit():
            return self._id_param.get_value(val)
        return self._str_param.get_value(val)


class BoolParameter(Parameter):
    """Representa un parámetro de tipo booleano.

    Se heredan las propiedades y métodos de la clase Parameter, definiendo
    nuevamente el método '_parse_value' para implementar lógica de parseo y
    validación propias de BoolParameter.

    """

    def __init__(self):
        super().__init__(False, False, [True, False])

    def _parse_value(self, val):
        # Cualquier valor recibido (no nulo) es verdadero
        return val is not None


class FieldListParameter(Parameter):
    """Representa un parámetro de tipo lista de campos.

    Se heredan las propiedades y métodos de la clase Parameter, definiendo
    nuevamente el método '_parse_value' para implementar lógica de parseo y
    validación propias de FieldListParameter. Se define también el método
    _check_value_in_choices para modificar su comportamiento original.

    Attributes:
        self._basic (set): Conjunto de campos mínimos, siempre son incluídos
            en cualquier lista de campos, incluso si el usuario no los
            especificó.
        self._standard (set): Conjunto de campos estándar. Se retorna este
            conjunto de parámetros como default cuando no se especifica ningún
            conjunto de parámetros.
        self._complete (set): Conjunto de campos completos. Este conjunto
            contiene todos los campos posibles a especificar.

    """

    def __init__(self, basic=None, standard=None, complete=None):
        self._basic = set(basic or [])
        self._standard = set(standard or []) | self._basic
        self._complete = set(complete or []) | self._standard

        super().__init__(False, list(self._standard), self._complete)

    def _check_value_in_choices(self, val):
        # La variable val es de tipo set o list, self._choices es de tipo set:
        # Lanzar una excepción si existen elementos en val que no están en
        # self._choices.
        if set(val) - self._complete:
            raise InvalidChoiceException(strings.FIELD_LIST_INVALID_CHOICE)

    def _expand_prefixes(self, received):
        """Dada un conjunto de campos recibidos, expande los campos con valores
        prefijos de otros.

        Por ejemplo, el valor 'provincia' se expande a 'provincia.id' y
        'provincia.nombre'. 'altura' se expande a 'altura.fin.derecha',
        'altura.fin.izquierda', etc.

        Args:
            received (set): Campos recibidos.

        Returns:
            set: Conjunto de campos con campos prefijos expandidos.

        """
        expanded = set()
        prefixes = set()

        for part in received:
            for field in self._complete:
                field_prefix = '.'.join(field.split('.')[:-1]) + '.'

                if field_prefix.startswith(part + '.'):
                    expanded.add(field)
                    prefixes.add(part)

        # Resultado: campos recibidos, menos los prefijos, con los campos
        # expandidos.
        return (received - prefixes) | expanded

    def _parse_value(self, val):
        if not val:
            raise ValueError(strings.FIELD_LIST_EMPTY)

        parts = [part.strip() for part in val.split(',')]

        # Manejar casos especiales: basico, estandar y completo
        if len(parts) == 1 and parts[0] in [N.BASIC, N.STANDARD, N.COMPLETE]:
            if parts[0] == N.BASIC:
                return list(self._basic)
            if parts[0] == N.STANDARD:
                return list(self._standard)
            if parts[0] == N.COMPLETE:
                return list(self._complete)

        received = set(parts)
        if len(parts) != len(received):
            raise ValueError(strings.FIELD_LIST_REPEATED)

        received = self._expand_prefixes(received)

        # Siempre se agregan los valores básicos
        return list(self._basic | received)


class IntParameter(Parameter):
    """Representa un parámetro de tipo entero.

    Se heredan las propiedades y métodos de la clase Parameter, definiendo
    nuevamente el método '_parse_value' para implementar lógica de parseo y
    validación propias de IntParameter, y 'valid_values' para validar uno
    o más parámetros 'max' recibidos en conjunto.

    """

    def __init__(self, required=False, default=0, choices=None,
                 lower_limit=None, upper_limit=None):
        self._lower_limit = lower_limit
        self._upper_limit = upper_limit
        super().__init__(required, default, choices)

    def _parse_value(self, val):
        try:
            int_val = int(val)
        except ValueError:
            raise ValueError(strings.INT_VAL_ERROR)

        if self._lower_limit is not None and int_val < self._lower_limit:
            raise ValueError(strings.INT_VAL_SMALL.format(self._lower_limit))

        if self._upper_limit is not None and int_val > self._upper_limit:
            raise ValueError(strings.INT_VAL_BIG.format(self._upper_limit))

        return int_val


class FloatParameter(Parameter):
    """Representa un parámetro de tipo float.

    Se heredan las propiedades y métodos de la clase Parameter, definiendo
    nuevamente el método '_parse_value' para implementar lógica de parseo y
    validación propias de FloatParameter.

    """

    def _parse_value(self, val):
        try:
            return float(val)
        except ValueError:
            raise ValueError(strings.FLOAT_VAL_ERROR)


class AddressParameter(Parameter):
    """Representa un parámetro de tipo dirección de calle (nombre y altura).

    Se heredan las propiedades y métodos de la clase Parameter, definiendo
    nuevamente el método '_parse_value' para implementar lógica de parseo y
    validación propias de AddressParameter.

    TODO: El análisis del campo 'direccion' es una tarea compleja y no debería
    resolverse utilizando expresiones regulares. Se debería implementar algún
    método más efectivo, que probablemente tenga una complejidad mucho mayor.
    Como referencia, ver: https://github.com/openvenues/libpostal. La
    implementación de la solución probablemente sea un proyecto en sí.

    """

    def __init__(self):
        super().__init__(required=True)

    def _parse_value(self, val):
        if not val:
            raise ValueError(strings.STRING_EMPTY)

        # 1) Remover ítems entre paréntesis e indicadores de número (N°, n°)
        val = re.sub(r'\(.*?\)|[nN][°º]', '', val.strip('\'" '))

        parts = [
            # 3) Normalizar espacios
            ' '.join(part.strip().split())
            for part
            # 2) Dividir el texto utilizando guiones, comas e indicadores
            # de barrio (B°, b°)
            in re.split(r'-|,|[bB][°º]', val)
            if part
        ]

        address = None
        for part in parts:
            # 4) Por cada parte de texto resultante, buscar un nombre de calle
            # junto a una altura numérica. La altura debe estar al final del
            # texto. Priorizar los primeros resultados válidos encontrados.
            match = re.search(r'^(.+?)\s+([0-9]+)$', part)
            if match:
                name, num_str = match.groups()
                num = int(num_str)

                if num > 0:
                    address = name, num
                    break
                else:
                    raise ValueError(strings.ADDRESS_INVALID_NUM)

        # 5) Último intento: tomar la primera parte de la dirección (que ya se
        # sabe que no tiene número) y utilizarla como nombre de calle.
        if not address:
            if parts and parts[0]:
                address = parts[0], None  # Dirección sin altura
            else:
                raise ParameterValueError(strings.ADDRESS_FORMAT,
                                          strings.ADDRESS_FORMAT_HELP)

        return address


class IntersectionParameter(Parameter):
    """Representa un parámetro utilizado para especificar búsqueda de entidades
    por intersección geográfica.

    Se heredan las propiedades y métodos de la clase Parameter, definiendo
    nuevamente el método '_parse_value' para implementar lógica de parseo y
    validación propias de IntersectionParameter.

    """

    def __init__(self, entities, required=False):
        """Inicializa un objeto de tipo IntersectionParameter.

        Args:
            entities (list): Lista de tipos de entidades que debería aceptar el
                parámetro a inicializar.
            required (bool): Indica si el parámetro HTTP debería ser
                obligatorio.

        """
        if any(e not in [N.STATE, N.DEPT, N.MUN] for e in entities):
            raise ValueError('Unknown entity type')

        self._id_params = {}

        if N.STATE in entities:
            self._id_params[N.STATE] = IdParameter(constants.STATE_ID_LEN)
        if N.DEPT in entities:
            self._id_params[N.DEPT] = IdParameter(constants.DEPT_ID_LEN)
        if N.MUN in entities:
            self._id_params[N.MUN] = IdParameter(constants.MUNI_ID_LEN)

        super().__init__(required)

    def _parse_value(self, val):
        """Toma un string con una lista de tipos de entidades con IDs, y
        retorna un diccionario con los IDs asociados a los tipos.

        El formato del string debe ser el siguiente:

            <tipo 1>:<ID 1>[:<ID 2>...][,<tipo 2>:<ID 1>[:<ID 2>...]...]

        Por ejemplo:

            provincia:02,departamento:90098:02007

        Args:
            val (str): Valor del parámetro recibido vía HTTP.

        Raises:
            ValueError: En caso de que el string recibido no tenga el formato
                adecuado.

        Returns:
            dict: Tipos de entidades asociados a conjuntos de IDs

        """
        if not val:
            raise ValueError(strings.STRING_EMPTY)

        ids = defaultdict(set)

        for part in [p.strip() for p in val.split(',')]:
            sections = [s.strip() for s in part.split(':')]
            if len(sections) < 2:
                raise ParameterValueError(
                    strings.FIELD_INTERSECTION_FORMAT,
                    strings.FIELD_INTERSECTION_FORMAT_HELP)

            entity = sections[0]
            if entity not in self._id_params:
                raise ParameterValueError(
                    strings.FIELD_INTERSECTION_FORMAT,
                    strings.FIELD_INTERSECTION_FORMAT_HELP)

            for entry in sections[1:]:
                if entity == N.STATE:
                    ids[N.STATES].add(
                        self._id_params[entity].get_value(entry))
                elif entity == N.DEPT:
                    ids[N.DEPARTMENTS].add(
                        self._id_params[entity].get_value(entry))
                elif entity == N.MUN:
                    ids[N.MUNICIPALITIES].add(
                        self._id_params[entity].get_value(entry))

        return ids if any(list(ids.values())) else {}


class ParamValidator:
    """Interfaz para realizar una validación de valores de parámetros HTTP.

    Los validadores deben definir un solo método, 'validate_values'.

    """

    def validate_values(self, param_names, values):
        """Realizar una validación de parámetros.

        El método 'validate_values' puede ser llamado en dos contextos:

        1) Al momento de validar valores para un conjunto de parámetros
            distintos. Por ejemplo, el valor de 'max' e 'inicio'. En este caso,
            param_names es un listado de todos los parámetros a validar.

        2) Al momento de validar varios valores para un mismo parámetro (por
            ejemplo, varios valores de 'max' en una request POST). En este
            caso, el valor de param_names es una lista de un solo nombre de
            parámetro.

        Args:
            param_names (list): Lista de nombres de parámetros.
            values (list): Lista de valores leídos y convertidos.

        Raises:
            ValueError: En caso de fallar la validación.

        """
        raise NotImplementedError()


class IntSetSumValidator(ParamValidator):
    """Implementa una validación de parámetros que comprueba que uno o más
    valores sumados no superen un cierto valor.

    Ver la documentación de 'ParamValidator' para detalles de uso.

    Attributes:
        _upper_limit (int): Suma máxima permitida.

    """

    def __init__(self, upper_limit):
        self._upper_limit = upper_limit

    def validate_values(self, param_names, values):
        if sum(values) > self._upper_limit:
            names = ', '.join('\'{}\''.format(name) for name in param_names)
            raise ValueError(
                strings.INT_VAL_BIG_GLOBAL.format(names, self._upper_limit))


class EndpointParameters():
    """Representa un conjunto de parámetros para un endpoint HTTP.

    Attributes:
        _get_qs_params (dict): Diccionario de parámetros aceptados vía
            querystring en requests GET, siendo las keys los nombres de los
            parámetros que se debe usar al especificarlos, y los valores
            objetos de tipo Parameter.

        _shared_params (dict): Similar a 'get_qs_params', pero contiene
            parámetros aceptados vía querystring en requests GET Y parámetros
            aceptados vía body en requests POST (compartidos).

        _cross_validators (list): Lista de tuplas (validador, [nombres]), que
            representa los validadores utilizados para validar distintos
            parámetros como conjuntos. Por ejemplo, los parámetros 'max' e
            'inicio' deben cumplir, en conjunto, la condición de no sumar
            más de un valor específico.

        _set_validators (dict): Diccionario de (nombre de parámetro -
            validador), utilizado para realizar validaciones sobre conjuntos de
            valores para un mismo parámetro. Este tipo de validaciones es
            utilizado cuando se procesan los requests POST, donde el usuario
            puede enviar varias consultas, con parámetros repetidos entre
            consultas.

    """

    def __init__(self, shared_params=None, get_qs_params=None):
        """Inicializa un objeto de tipo EndpointParameters.

        Args:
            get_qs_params (dict): Ver atributo 'get_qs_params'.
            shared_params (dict): Ver atributo 'shared_params'.

        """
        shared_params = shared_params or {}
        get_qs_params = get_qs_params or {}

        self._get_qs_params = {**get_qs_params, **shared_params}
        self._post_body_params = shared_params

        self._cross_validators = []
        self._set_validators = defaultdict(list)

    def with_cross_validator(self, param_names, validator):
        """Agrega un validador a la lista de validadores para grupos de
        parámetros.

        Args:
            param_names (list): Lista de nombres de parámetros sobre los cuales
                ejecutar el validador.
            validator (ParamValidator): Validador de valores.

        """
        self._cross_validators.append((validator, param_names))
        return self

    def with_set_validator(self, param_name, validator):
        """Agrega un validador a la lista de validadores para conjuntos de
        valores para un parámetro.

        Args:
            param_name (str): Nombre del parámetro a utilizar en la validación
                de conjuntos de valores.
            validator (ParamValidator): Validador de valores.

        """
        self._set_validators[param_name].append(validator)
        return self

    def parse_params_dict(self, params, received, from_source):
        """Parsea parámetros (clave-valor) recibidos en una request HTTP,
        utilizando el conjunto 'params' de parámetros.

        Args:
            params (dict): Diccionario de objetos Parameter (nombre-Parameter).
            received (dict): Parámetros recibidos sin procesar (nombre-valor).
            from_source (str): Ubicación dentro de la request HTTP donde fueron
                recibidos los parámetros.

        Returns:
            list: Lista de resultados. Los resultados consisten de un
                diccionario conteniendo como clave el nombre del parámetro, y
                como valor el valor parseado y validado, con su tipo apropiado.

        Raises:
            ParameterParsingException: Excepción con errores de parseo
                de parámetros.

        """
        parsed, errors = {}, {}
        is_multi_dict = hasattr(received, 'getlist')

        for param_name, param in params.items():
            received_val = received.get(param_name)

            if is_multi_dict and len(received.getlist(param_name)) > 1:
                errors[param_name] = ParamError(ParamErrorType.REPEATED,
                                                strings.REPEATED_ERROR,
                                                from_source)
                continue

            try:
                parsed[param_name] = param.get_value(received_val)
            except ParameterRequiredException:
                errors[param_name] = ParamError(ParamErrorType.PARAM_REQUIRED,
                                                strings.MISSING_ERROR.format(
                                                    param_name),
                                                from_source)
            except ValueError as e:
                errors[param_name] = ParamError(ParamErrorType.VALUE_ERROR,
                                                str(e), from_source)
            except ParameterValueError as e:
                errors[param_name] = ParamError(ParamErrorType.VALUE_ERROR,
                                                e.message, from_source, e.help)
            except InvalidChoiceException as e:
                errors[param_name] = ParamError(ParamErrorType.INVALID_CHOICE,
                                                str(e), from_source,
                                                param.choices)

        for param_name in received:
            if param_name not in params:
                errors[param_name] = ParamError(ParamErrorType.UNKNOWN_PARAM,
                                                strings.UNKNOWN_ERROR,
                                                from_source,
                                                list(params.keys()))

        if errors:
            raise ParameterParsingException(errors)

        self.cross_validate_params(parsed)
        return parsed

    def cross_validate_params(self, parsed):
        """Ejecuta las validaciones de conjuntos de parámetros.

        Args:
            parsed (dict): Diccionario parámetro-valor donde se almacenan los
                resultados del parseo de argumentos para una consulta.

        Raises:
            ParameterParsingException: Se lanza la excepción si no se pasó una
                validación instalada para conjuntos de parámetros.

        """
        errors = {}

        for validator, param_names in self._cross_validators:
            values = [parsed[name] for name in param_names]
            try:
                validator.validate_values(param_names, values)
            except ValueError as e:
                for param in param_names:
                    errors[param] = ParamError(ParamErrorType.INVALID_SET,
                                               str(e), param)

                # Si se encontraron errores al validar uno o más parámetros,
                # utilizar el primer error encontrado.
                break

        if errors:
            raise ParameterParsingException(errors)

    def validate_param_sets(self, results):
        """Ejecuta las validaciones de conjuntos de valores sobre todos los
        parámetros aceptados por el objeto EndpointParameters.

        Args:
            results (list): Lista de diccionarios, cada diccionario contiene
                los resultados de parsear los parámetros de una consulta.

        Raises:
            ParameterParsingException: Se lanza la excepción si no se pasó una
                validación instalada para conjuntos de valores.

        """
        # Comenzar con un diccionario de errores vacío por cada consulta.
        errors_list = [{}] * len(results)

        for name in self._post_body_params.keys():
            validators = self._set_validators[name]

            for validator in validators:
                try:
                    # Validar conjuntos de valores de parámetros bajo el
                    # mismo nombre
                    validator.validate_values([name],
                                              (result[name]
                                               for result in results))
                except ValueError as e:
                    error = ParamError(ParamErrorType.INVALID_SET, str(e),
                                       'body')

                    # Si la validación no fue exitosa, crear un error y
                    # agregarlo al conjunto de errores de cada consulta que lo
                    # utilizó.
                    for errors in errors_list:
                        errors[name] = error

                    # Se muestra solo el error de la primera validación
                    # fallida.
                    break

        # Luego de validar conjuntos, lanzar una excepción si se generaron
        # errores nuevos
        if any(errors_list):
            raise ParameterParsingException(errors_list)

    def parse_post_params(self, qs_params, body, body_key):
        """Parsea parámetros (clave-valor) recibidos en una request HTTP
        POST utilizando el conjunto de parámetros internos. Se parsean por
        separado los parámetros querystring y los parámetros de body.

        Args:
            qs_params (dict): Parámetros recibidos en el query string.
            body_params (dict): Datos JSON recibidos vía POST.
            body_key (str): Nombre de la key bajo donde debería estar la lista
                de consultas recibias vía POST, en 'body_params'.

        Returns:
            list: lista de conjuntos de parámetros parseados provienentes
                de 'parse_param_dict'.

        Raises:
            ParameterParsingException: Excepción con errores de parseo
                de parámetros.

        """
        if qs_params:
            # No aceptar parámetros de querystring en bulk
            raise ParameterParsingException([
                {'querystring': ParamError(ParamErrorType.INVALID_LOCATION,
                                           strings.BULK_QS_INVALID,
                                           'querystring')}
            ])

        body_params = None
        if isinstance(body, dict):
            body_params = body.get(body_key)

        if not body_params or not isinstance(body_params, list):
            # No aceptar operaciones bulk que no sean listas, y no
            # aceptar listas vacías.
            raise ParameterParsingException([
                {body_key: ParamError(ParamErrorType.INVALID_BULK,
                                      strings.INVALID_BULK.format(body_key),
                                      'body')}
            ])

        if len(body_params) > MAX_RESULT_LEN:
            raise ParameterParsingException([
                {body_key: ParamError(
                    ParamErrorType.INVALID_BULK_LEN,
                    strings.BULK_LEN_ERROR.format(MAX_RESULT_LEN), 'body')}
            ])

        results, errors_list = [], []
        for param_dict in body_params:
            parsed, errors = {}, {}
            if hasattr(param_dict, 'get'):
                try:
                    parsed = self.parse_params_dict(self._post_body_params,
                                                    param_dict, 'body')
                except ParameterParsingException as e:
                    errors = e.errors
            else:
                errors[body_key] = ParamError(
                    ParamErrorType.INVALID_BULK_ENTRY,
                    strings.INVALID_BULK_ENTRY, 'body')

            results.append(parsed)
            errors_list.append(errors)

        if any(errors_list):
            raise ParameterParsingException(errors_list)

        self.validate_param_sets(results)
        return results

    def parse_get_params(self, qs_params):
        """Parsea parámetros (clave-valor) recibidos en una request HTTP GET
        utilizando el conjunto de parámetros internos.

        Args:
            qs_params (dict): Parámetros recibidos en el query string.

        Returns:
            list: Valor de retorno de 'parse_dict_params'.

        Raises:
            ParameterParsingException: Excepción con errores de parseo
                de parámetros.

        """
        return self.parse_params_dict(self._get_qs_params, qs_params,
                                      'querystring')


PARAMS_COUNTRIES = EndpointParameters(shared_params={
    N.NAME: StrParameter(),
    N.ORDER: StrParameter(choices=[N.NAME]),
    N.FLATTEN: BoolParameter(),
    N.FIELDS: FieldListParameter(basic=[N.NAME],
                                 standard=[N.C_LAT, N.C_LON],
                                 complete=[N.SOURCE]),
    N.MAX: IntParameter(default=10, lower_limit=1, upper_limit=MAX_RESULT_LEN),
    N.OFFSET: IntParameter(lower_limit=0, upper_limit=MAX_RESULT_WINDOW),
    N.EXACT: BoolParameter()
}, get_qs_params={
    N.FORMAT: StrParameter(default='json', choices=['json', 'csv', 'geojson'])
}).with_set_validator(
    N.MAX,
    IntSetSumValidator(upper_limit=MAX_RESULT_LEN)
).with_cross_validator(
    [N.MAX, N.OFFSET],
    IntSetSumValidator(upper_limit=MAX_RESULT_WINDOW)
)


PARAMS_STATES = EndpointParameters(shared_params={
    N.ID: IdParameter(length=constants.STATE_ID_LEN),
    N.NAME: StrParameter(),
    N.INTERSECTION: IntersectionParameter(entities=[N.DEPT, N.MUN]),
    N.ORDER: StrParameter(choices=[N.ID, N.NAME]),
    N.FLATTEN: BoolParameter(),
    N.FIELDS: FieldListParameter(basic=[N.ID, N.NAME],
                                 standard=[N.C_LAT, N.C_LON],
                                 complete=[N.SOURCE]),
    N.MAX: IntParameter(default=24, lower_limit=1, upper_limit=MAX_RESULT_LEN),
    N.OFFSET: IntParameter(lower_limit=0, upper_limit=MAX_RESULT_WINDOW),
    N.EXACT: BoolParameter()
}, get_qs_params={
    N.FORMAT: StrParameter(default='json', choices=['json', 'csv', 'geojson'])
}).with_set_validator(
    N.MAX,
    IntSetSumValidator(upper_limit=MAX_RESULT_LEN)
).with_cross_validator(
    [N.MAX, N.OFFSET],
    IntSetSumValidator(upper_limit=MAX_RESULT_WINDOW)
)

PARAMS_DEPARTMENTS = EndpointParameters(shared_params={
    N.ID: IdParameter(length=constants.DEPT_ID_LEN),
    N.NAME: StrParameter(),
    N.INTERSECTION: IntersectionParameter(entities=[N.STATE, N.MUN]),
    N.STATE: StrOrIdParameter(id_length=constants.STATE_ID_LEN),
    N.ORDER: StrParameter(choices=[N.ID, N.NAME]),
    N.FLATTEN: BoolParameter(),
    N.FIELDS: FieldListParameter(basic=[N.ID, N.NAME],
                                 standard=[N.C_LAT, N.C_LON, N.STATE_ID,
                                           N.STATE_NAME],
                                 complete=[N.SOURCE, N.STATE_INTERSECTION]),
    N.MAX: IntParameter(default=10, lower_limit=1, upper_limit=MAX_RESULT_LEN),
    N.OFFSET: IntParameter(lower_limit=0, upper_limit=MAX_RESULT_WINDOW),
    N.EXACT: BoolParameter()
}, get_qs_params={
    N.FORMAT: StrParameter(default='json', choices=['json', 'csv', 'geojson'])
}).with_set_validator(
    N.MAX,
    IntSetSumValidator(upper_limit=MAX_RESULT_LEN)
).with_cross_validator(
    [N.MAX, N.OFFSET],
    IntSetSumValidator(upper_limit=MAX_RESULT_WINDOW)
)

PARAMS_MUNICIPALITIES = EndpointParameters(shared_params={
    N.ID: IdParameter(length=constants.MUNI_ID_LEN),
    N.NAME: StrParameter(),
    N.INTERSECTION: IntersectionParameter(entities=[N.DEPT, N.STATE]),
    N.STATE: StrOrIdParameter(id_length=constants.STATE_ID_LEN),
    N.ORDER: StrParameter(choices=[N.ID, N.NAME]),
    N.FLATTEN: BoolParameter(),
    N.FIELDS: FieldListParameter(basic=[N.ID, N.NAME],
                                 standard=[N.C_LAT, N.C_LON, N.STATE_ID,
                                           N.STATE_NAME, N.DEPT_ID],
                                 complete=[N.SOURCE, N.STATE_INTERSECTION]),
    N.MAX: IntParameter(default=10, lower_limit=1, upper_limit=MAX_RESULT_LEN),
    N.OFFSET: IntParameter(lower_limit=0, upper_limit=MAX_RESULT_WINDOW),
    N.EXACT: BoolParameter()
}, get_qs_params={
    N.FORMAT: StrParameter(default='json', choices=['json', 'csv', 'geojson'])
}).with_set_validator(
    N.MAX,
    IntSetSumValidator(upper_limit=MAX_RESULT_LEN)
).with_cross_validator(
    [N.MAX, N.OFFSET],
    IntSetSumValidator(upper_limit=MAX_RESULT_WINDOW)
)

PARAMS_LOCALITIES = EndpointParameters(shared_params={
    N.ID: IdParameter(length=constants.LOCALITY_ID_LEN),
    N.NAME: StrParameter(),
    N.STATE: StrOrIdParameter(id_length=constants.STATE_ID_LEN),
    N.DEPT: StrOrIdParameter(id_length=constants.DEPT_ID_LEN),
    N.MUN: StrOrIdParameter(id_length=constants.MUNI_ID_LEN),
    N.ORDER: StrParameter(choices=[N.ID, N.NAME]),
    N.FLATTEN: BoolParameter(),
    N.FIELDS: FieldListParameter(basic=[N.ID, N.NAME],
                                 standard=[N.C_LAT, N.C_LON, N.STATE_ID,
                                           N.STATE_NAME, N.DEPT_ID,
                                           N.DEPT_NAME, N.MUN_ID, N.MUN_NAME,
                                           N.LOCALITY_TYPE],
                                 complete=[N.SOURCE]),
    N.MAX: IntParameter(default=10, lower_limit=1, upper_limit=MAX_RESULT_LEN),
    N.OFFSET: IntParameter(lower_limit=0, upper_limit=MAX_RESULT_WINDOW),
    N.EXACT: BoolParameter()
}, get_qs_params={
    N.FORMAT: StrParameter(default='json', choices=['json', 'csv', 'geojson'])
}).with_set_validator(
    N.MAX,
    IntSetSumValidator(upper_limit=MAX_RESULT_LEN)
).with_cross_validator(
    [N.MAX, N.OFFSET],
    IntSetSumValidator(upper_limit=MAX_RESULT_WINDOW)
)

PARAMS_ADDRESSES = EndpointParameters(shared_params={
    N.ADDRESS: AddressParameter(),
    N.ROAD_TYPE: StrParameter(),
    N.STATE: StrOrIdParameter(id_length=constants.STATE_ID_LEN),
    N.DEPT: StrOrIdParameter(id_length=constants.DEPT_ID_LEN),
    N.ORDER: StrParameter(choices=[N.ID, N.NAME]),
    N.FLATTEN: BoolParameter(),
    N.FIELDS: FieldListParameter(basic=[N.ID, N.NAME, N.DOOR_NUM],
                                 standard=[N.STATE_ID, N.STATE_NAME, N.DEPT_ID,
                                           N.DEPT_NAME, N.ROAD_TYPE,
                                           N.FULL_NAME, N.LOCATION_LAT,
                                           N.LOCATION_LON],
                                 complete=[N.SOURCE]),
    N.MAX: IntParameter(default=10, lower_limit=1, upper_limit=MAX_RESULT_LEN),
    N.OFFSET: IntParameter(lower_limit=0, upper_limit=MAX_RESULT_WINDOW),
    N.EXACT: BoolParameter()
}, get_qs_params={
    N.FORMAT: StrParameter(default='json', choices=['json', 'csv', 'geojson'])
}).with_set_validator(
    N.MAX,
    IntSetSumValidator(upper_limit=MAX_RESULT_LEN)
).with_cross_validator(
    [N.MAX, N.OFFSET],
    IntSetSumValidator(upper_limit=MAX_RESULT_WINDOW)
)

PARAMS_STREETS = EndpointParameters(shared_params={
    N.ID: IdParameter(length=constants.STREET_ID_LEN),
    N.NAME: StrParameter(),
    N.ROAD_TYPE: StrParameter(),
    N.STATE: StrOrIdParameter(id_length=constants.STATE_ID_LEN),
    N.DEPT: StrOrIdParameter(id_length=constants.DEPT_ID_LEN),
    N.ORDER: StrParameter(choices=[N.ID, N.NAME]),
    N.FLATTEN: BoolParameter(),
    N.FIELDS: FieldListParameter(basic=[N.ID, N.NAME],
                                 standard=[N.START_R, N.START_L, N.END_R,
                                           N.END_L, N.STATE_ID, N.STATE_NAME,
                                           N.DEPT_ID, N.DEPT_NAME, N.FULL_NAME,
                                           N.ROAD_TYPE],
                                 complete=[N.SOURCE]),
    N.MAX: IntParameter(default=10, lower_limit=1, upper_limit=MAX_RESULT_LEN),
    N.OFFSET: IntParameter(lower_limit=0, upper_limit=MAX_RESULT_WINDOW),
    N.EXACT: BoolParameter()
}, get_qs_params={
    N.FORMAT: StrParameter(default='json', choices=['json', 'csv'])
}).with_set_validator(
    N.MAX,
    IntSetSumValidator(upper_limit=MAX_RESULT_LEN)
).with_cross_validator(
    [N.MAX, N.OFFSET],
    IntSetSumValidator(upper_limit=MAX_RESULT_WINDOW)
)


PARAMS_PLACE = EndpointParameters(shared_params={
    N.LAT: FloatParameter(required=True),
    N.LON: FloatParameter(required=True),
    N.FLATTEN: BoolParameter(),
    N.FIELDS: FieldListParameter(basic=[N.STATE_ID, N.STATE_NAME, N.LAT,
                                        N.LON],
                                 standard=[N.DEPT_ID, N.DEPT_NAME, N.MUN_ID,
                                           N.MUN_NAME],
                                 complete=[N.SOURCE])
}, get_qs_params={
    N.FORMAT: StrParameter(default='json', choices=['json', 'geojson'])
})
