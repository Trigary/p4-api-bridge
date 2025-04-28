import abc
import dataclasses
from pathlib import Path
from typing import Dict


class SwitchApiConfig(abc.ABC):
    """
    Defines how the control plane can communicate with a switch.
    Each subclass defines different parameters, connection methods, and they may require different dependencies.
    Always make sure to check the documentation of the subclass to see what is required.
    """
    pass


@dataclasses.dataclass(frozen=True)
class SimpleSwitchThriftApiConfig(SwitchApiConfig):
    """
    Defines the connection parameters for the SimpleSwitch Thrift API.
    Depends on: https://github.com/nsg-ethz/p4-utils
    """
    thrift_port: int
    """Port at which the switch is listening for Thrift connections."""
    interface_to_port: Dict[str, int]
    """Mapping of network interface names to port IDs. See the ApiBridge class documentation for more information."""


@dataclasses.dataclass(frozen=True)
class SimpleSwitchP4RuntimeApiConfig(SwitchApiConfig):
    """
    Defines the connection parameters for the SimpleSwitch P4 Runtime API.
    Depends on: https://github.com/nsg-ethz/p4-utils
    """
    device_id: int
    grpc_port: int
    """Port at which the switch is listening for gRPC connections."""
    switch_p4rt_path: Path
    """Path of the P4Runtime JSON file."""
    switch_json_path: Path
    """Path of the JSON file containing the P4 program."""
    interface_to_port: Dict[str, int]
    """Mapping of network interface names to port IDs. See the ApiBridge class documentation for more information."""


@dataclasses.dataclass(frozen=True)
class NikssCtlApiConfig(SwitchApiConfig):
    """
    Defines the parameters for controlling eBPF-based NIKSS switches through the NIKSS command line interface.
    The interface to port mappings are automatically queried at runtime via the NIKSS API.
    No Python dependencies are required, but the nikss-ctl command must be available in the PATH.
    """
    pipeline_id: int
    """The identifier of the pipeline in which the P4 program is loaded."""


@dataclasses.dataclass(frozen=True)
class TofinoShellApiConfig(SwitchApiConfig):
    """
    Defines the parameters for controlling Tofino switches using a BF Runtime shell script.
    Sometimes, we may not want to run our entire control plane inside the BF shell.
    Using this method, we only need to run a small script with the BF shell that will listen for connections
    and execute the received commands, allowing us to run the rest of the control plane in a separate process.

    No Python dependencies are required, but the remote BF shell script (server) must be started manually:
    run_bfshell.sh -b <SCRIPT_PATH> -i

    The script can be downloaded from the version control system, but it's also available at the installation path.
    Its location can be found via the following shell command:
    python3 -c "from p4_api_bridge.impl import tofino as x ; print(x.__file__.replace('__init__', 'bfsh_server'))"
    """
    p4_program_name: str
    """Name of the P4 program loaded into the pipeline, usually the name of the .p4 file."""
    bfsh_server_port: int
    """Port at which the remote BF shell script is listening for connections."""
    interface_to_port: Dict[str, int]
    """Mapping of network interface names to port IDs. See the ApiBridge class documentation for more information."""
    enable_acknowledgments: bool = True
    """
    Whether the remote BF shell script should send an acknowledgment after executing a command.
    Acknowledgements force the control plane to wait for the command to finish executing before sending the next one.
    Without acknowledgements, the control plane can send multiple commands in parallel, which may be faster,
    but it may cause issues, especially if batching is not used.
    Without acknowledgments, it is also possible for the remote BF shell to fall behind in processing commands,
    without the control plane being aware of it.
    """


class SwitchBase:
    """
    Class containing the necessary fields for this library to interact with switches.
    Dependents of this library should inherit from this class in their own switch classes,
    that way this library can be used seamlessly:
    only their own switch instance would need to be passed as parameters when calling library functions.
    """

    def __init__(self, name: str, api_config: SwitchApiConfig) -> None:
        """
        Creates and initializes a new instance. Has no side effects.

        :param name: unique name of the switch (useful for logging, debugging, and as dictionary keys)
        :param api_config: defines the connection parameters for the switch
        """
        self._name = name
        self._api_config = api_config

    @property
    def name(self) -> str:
        """The unique name of the switch, useful for logging, debugging, and as dictionary keys."""
        return self._name

    @property
    def api_config(self) -> SwitchApiConfig:
        """Defines the connection parameters for the switch."""
        return self._api_config
