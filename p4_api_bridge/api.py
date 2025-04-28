import abc
import dataclasses
import logging
from typing import Callable, Dict, List, Optional, Union

from p4_api_bridge.config import NikssCtlApiConfig, SimpleSwitchP4RuntimeApiConfig, SimpleSwitchThriftApiConfig, \
    SwitchBase, TofinoShellApiConfig

_logger: logging.Logger = logging.getLogger(__name__)


class ApiBridgeFactory:
    """
    Creates and caches an API bridge instance for switches.
    Instances should be closed when they are no longer needed, using e.g. the close() method.
    """

    def __init__(self) -> None:
        self._cache: Dict[str, 'ApiBridge'] = dict()  # Keys are switch names

    def get(self, switch: SwitchBase) -> 'ApiBridge':
        """Gets the API bridge for the given switch, creating and caching it if necessary."""
        if switch.name not in self._cache:
            self._cache[switch.name] = ApiBridgeFactory.create_for(switch)
        return self._cache[switch.name]

    def close(self) -> None:
        """Closes all cached API bridges."""
        for bridge in self._cache.values():
            bridge.close()
        self._cache.clear()

    @staticmethod
    def create_for(switch: SwitchBase) -> 'ApiBridge':
        """
        Creates a new API bridge instance for the specified switch.
        Most of the time this method should not be called directly, because it doesn't cache the returned instance.
        """
        name, config = switch.name, switch.api_config
        if isinstance(config, SimpleSwitchThriftApiConfig):
            from p4_api_bridge.impl.thrift import SimpleSwitchThriftApiBridge
            return SimpleSwitchThriftApiBridge(name, config.thrift_port, config.interface_to_port)
        if isinstance(config, SimpleSwitchP4RuntimeApiConfig):
            from p4_api_bridge.impl.p4runtime import SimpleSwitchP4RuntimeApiBridge
            return SimpleSwitchP4RuntimeApiBridge(name, config.device_id, config.grpc_port,
                                                  config.switch_p4rt_path, config.switch_json_path,
                                                  config.interface_to_port)
        if isinstance(config, NikssCtlApiConfig):
            from p4_api_bridge.impl.nikss import NikssCtlApiBridge
            return NikssCtlApiBridge(name, config.pipeline_id)
        if isinstance(config, TofinoShellApiConfig):
            from p4_api_bridge.impl.tofino import TofinoShellApiBridge
            return TofinoShellApiBridge(name, config.p4_program_name, config.bfsh_server_port,
                                        config.interface_to_port, config.enable_acknowledgments)
        else:
            raise RuntimeError(f"Switch {name} has unknown switch api config type: {config}")


class SwitchApiError(Exception):
    """
    Exception that wraps other exceptions raised when interacting with a switch.
    This exception is used to provide a consistent error handling mechanism across different switch APIs.
    """

    def __init__(self, message: str):
        super().__init__(message)


def _wrap_switch_error(func: Callable) -> Callable:
    """Decorator that wraps all raised exceptions with a SwitchApiError."""

    def wrapper(*args, **kwargs) -> object:
        try:
            return func(*args, **kwargs)
        except SwitchApiError:
            raise  # Already a SwitchApiError, no need to wrap it
        except Exception as e:
            raise SwitchApiError(f"Inner exception: {type(e).__name__}: {e}") from e

    return wrapper


class BatchScope:
    """Context manager that starts and ends a batch of operations."""

    def __init__(self, on_enter: Callable, on_exit: Callable):
        self._on_enter: Callable = on_enter
        self._on_exit: Callable = on_exit

    def __enter__(self) -> None:
        self._on_enter()

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self._on_exit()


class ApiBridge(abc.ABC):
    """
    Different switches use different control plane APIs. This class abstracts the differences away, providing
    a common interface for controlling P4 programmable switches.
    Please note that some features may not be supported by all implementations, or they might have minor differences.

    There are various rules constraining what kind of parameters should be passed to the methods of this class:
    - When specifying a name (register/table/action name), it must be a fully qualified name (e.g. MyIngress.my_table).

    Value parameters (register values, table keys, action parameters) undergo automatic translation:
    - If the value is recognized as a network interface (e.g. s1-eth3), it is translated to a numeric port ID (e.g. 3).
    """

    def __init__(self, switch: str) -> None:
        self._switch: str = switch
        _logger.debug(f"{switch}: Using {self.__class__.__name__}")

    def _translate_name_if_necessary(self, value: str) -> str:
        """Executes the necessary validation and translations of table/action/register/etc names."""
        if "." not in value:
            raise ValueError(f"Table/action/register name '{value}' must be fully qualified (e.g. MyIngress.my_table)")
        return value

    def _translate_value_if_necessary(self, value: Union[str, int]) -> str:
        """
        Executes the necessary validation and translations of keys/parameters/values.
        This method supports various types (numbers, IP addresses, MAC addresses)
        and even non-exact match keys such as range match or LPM match.
        """
        if not isinstance(value, str):
            return str(value)  # Return integers or other number types as-is
        if (port_id := self.translate_interface_to_port(value)) is not None:
            return str(port_id)
        return value

    @abc.abstractmethod
    def translate_interface_to_port(self, intf: str) -> Optional[int]:
        """
        Translates a network interface name (e.g. s1-eth3) to a numeric port ID (e.g. 3) used within P4 code.
        None is returned if the specified interface is not valid.
        """

    @_wrap_switch_error
    def close(self) -> None:
        """Shuts this API bridge instance down. This method should be called when the API bridge is no longer needed."""
        _logger.debug(f"{self._switch}: Closing API bridge")
        return self._close_impl()

    def _close_impl(self) -> None:
        """The actual implementation of close."""
        pass  # No-op by default

    @_wrap_switch_error
    def reset_state(self) -> None:
        """Clears the table entries, sets the registers to 0, resets the counters, etc."""
        _logger.debug(f"{self._switch}: Resetting state")
        return self._reset_state_impl()

    @abc.abstractmethod
    def _reset_state_impl(self) -> None:
        """The actual implementation of reset_state."""

    def try_create_batch(self) -> BatchScope:
        """
        Creates an object that can be used as a context manager to start and end a batch of operations
        (using the 'with' statement). Batch operations might not be supported by some implementations,
        in which case using batches will provide no performance improvement, but no errors will be raised either.
        """

        @_wrap_switch_error
        def batch_start() -> None:
            _logger.debug(f"{self._switch}: Starting batch")
            self._batch_start_impl()

        @_wrap_switch_error
        def batch_stop() -> None:
            _logger.debug(f"{self._switch}: Stopping batch")
            self._batch_stop_impl()

        return BatchScope(batch_start, batch_stop)

    def _batch_start_impl(self) -> None:
        """Starts a batch of operations. This method is allowed to be no-op if batching is not supported."""
        pass  # No-op by default

    def _batch_stop_impl(self) -> None:
        """Stops a batch of operations. This method is allowed to be no-op if batching is not supported."""
        pass  # No-op by default

    @_wrap_switch_error
    def register_set(self, register_name: str, index: int, value: Union[str, int]) -> None:
        """Sets the value of a register. May not be supported by all implementations."""
        _logger.debug(f"{self._switch}: Setting register {register_name} to {value}")
        register_name = self._translate_name_if_necessary(register_name)
        value = self._translate_value_if_necessary(value)
        _logger.debug(f"  after translation: {register_name} to {value}")
        return self._register_set_impl(register_name, index, value)

    @abc.abstractmethod
    def _register_set_impl(self, register_name: str, index: int, value: str) -> None:
        """The actual implementation of register_set, with the translations already executed."""

    @_wrap_switch_error
    def table_modify_or_add(self, already_added: bool, table_name: str, match_keys: List[Union[str, int]],
                            action_name: str, action_params: List[Union[str, int]]) -> None:
        """
        Modifies an existing table entry or adds a new one, depending on the value of the first parameter.
        This is a utility method designed to reduce boilerplate code:
        calling this method is equivalent to calling table_add or table_modify.
        """
        action = "Modifying" if already_added else "Adding"
        _logger.debug(f"{self._switch}: {action} table entry:"
                      f" {table_name} {match_keys} -> {action_name} {action_params}")
        table_name = self._translate_name_if_necessary(table_name)
        match_keys = [self._translate_value_if_necessary(key) for key in match_keys]
        action_name = self._translate_name_if_necessary(action_name)
        action_params = [self._translate_value_if_necessary(param) for param in action_params]
        _logger.debug(f"  after translation: {table_name} {match_keys} -> {action_name} {action_params}")
        if already_added:
            return self._table_modify_impl(table_name, match_keys, action_name, action_params)
        else:
            return self._table_add_impl(table_name, match_keys, action_name, action_params)

    @_wrap_switch_error
    def table_add(self, table_name: str, match_keys: List[Union[str, int]],
                  action_name: str, action_params: List[Union[str, int]]) -> None:
        """Adds a new table entry."""
        return self.table_modify_or_add(False, table_name, match_keys, action_name, action_params)

    @abc.abstractmethod
    def _table_add_impl(self, table_name: str, match_keys: List[str], action_name: str,
                        action_params: List[str]) -> None:
        """The actual implementation of table_add, with the translations already executed."""

    @_wrap_switch_error
    def table_modify(self, table_name: str, match_keys: List[Union[str, int]],
                     action_name: str, action_params: List[Union[str, int]]) -> None:
        """Modifies an existing table entry."""
        return self.table_modify_or_add(True, table_name, match_keys, action_name, action_params)

    @abc.abstractmethod
    def _table_modify_impl(self, table_name: str, match_keys: List[str], action_name: str,
                           action_params: List[str]) -> None:
        """The actual implementation of table_modify, with the translations already executed."""

    @_wrap_switch_error
    def table_set_default(self, table_name: str, action_name: str, action_params: List[Union[str, int]]) -> None:
        """Sets the default table action. See table_add for more details."""
        _logger.debug(f"{self._switch}: Setting default table action: {table_name} -> {action_name} {action_params}")
        table_name = self._translate_name_if_necessary(table_name)
        action_name = self._translate_name_if_necessary(action_name)
        action_params = [self._translate_value_if_necessary(param) for param in action_params]
        _logger.debug(f"  after translation: {table_name} -> {action_name} {action_params}")
        return self._table_set_default_impl(table_name, action_name, action_params)

    @abc.abstractmethod
    def _table_set_default_impl(self, table_name: str, action_name: str, action_params: List[str]) -> None:
        """The actual implementation of table_set_default, with the translations already executed."""

    @_wrap_switch_error
    def table_delete(self, table_name: str, match_keys: List[Union[str, int]]) -> None:
        """Deletes a specific entry from the a table."""
        _logger.debug(f"{self._switch}: Deleting table entry: {table_name} {match_keys}")
        table_name = self._translate_name_if_necessary(table_name)
        match_keys = [self._translate_value_if_necessary(key) for key in match_keys]
        _logger.debug(f"  after translation: {table_name} {match_keys}")
        return self._table_delete_impl(table_name, match_keys)

    @abc.abstractmethod
    def _table_delete_impl(self, table_name: str, match_keys: List[str]) -> None:
        """The actual implementation of table_delete, with the translations already executed."""

    @_wrap_switch_error
    def table_clear(self, table_name: str) -> None:
        """Deletes all entries from the specified table except the default action."""
        _logger.debug(f"{self._switch}: Clearing table: {table_name}")
        table_name = self._translate_name_if_necessary(table_name)
        _logger.debug(f"  after translation: {table_name}")
        return self._table_clear_impl(table_name)

    @abc.abstractmethod
    def _table_clear_impl(self, table_name: str) -> None:
        """The actual implementation of table_clear, with the translations already executed."""

    @dataclasses.dataclass(frozen=True)
    class MulticastGroupMember:
        """Container of configuration entries for a multicast group member."""
        egress_interface: str
        instance_id: int

    @_wrap_switch_error
    def multicast_group_create(self, group_id: int, members: List[MulticastGroupMember]) -> None:
        """Creates a multicast group."""
        _logger.debug(f"{self._switch}: Creating multicast group: {group_id} -> {members}")
        members = [dataclasses.replace(m, egress_interface=self._translate_value_if_necessary(m.egress_interface))
                   for m in members]
        _logger.debug(f"  after translation: {group_id} -> {members}")
        return self._multicast_group_create_impl(group_id, members)

    @abc.abstractmethod
    def _multicast_group_create_impl(self, group_id: int, members: List[MulticastGroupMember]) -> None:
        """The actual implementation of multicast_group_create, with the translations already executed."""

    @dataclasses.dataclass(frozen=True)
    class CloneSessionMember:
        """Container of configuration entries for a clone session member."""
        egress_interface: str
        instance_id: int
        class_of_service: Optional[int] = None
        truncate_after_packet_length: Optional[int] = None

    @_wrap_switch_error
    def clone_session_create(self, session_id: int, members: List[CloneSessionMember]) -> None:
        """
        Creates a clone session (also knows as a mirror session or packet mirroring session).
        Some implementations may only support a subset of the features: for example, class of service might not be
        supported, or all members might have to have the same truncation length.
        """
        _logger.debug(f"{self._switch}: Creating clone session: {session_id} -> {members}")
        members = [dataclasses.replace(m, egress_interface=self._translate_value_if_necessary(m.egress_interface))
                   for m in members]
        _logger.debug(f"  after translation: {session_id} -> {members}")
        return self._clone_session_create_impl(session_id, members)

    @abc.abstractmethod
    def _clone_session_create_impl(self, session_id: int, members: List[CloneSessionMember]) -> None:
        """The actual implementation of clone_session_create, with the translations already executed."""
