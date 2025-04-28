# P4 Control Plane API Bridge

This library allows you to use various control plane APIs through a shared interface.

Ideally, all switches should support P4Runtime directly, making this library unnecessary.
Unfortunately, this is not the case, and many switches have their own APIs.

## Installation

```shell
python3 -m pip install --upgrade pip
python3 -m pip install "p4-api-bridge @ git+https://github.com/Trigary/p4-api-bridge.git"
```

For alternative installation methods, please refer to the
[Python documentation](https://packaging.python.org/en/latest/guides/installing-using-pip-and-virtual-environments/#install-packages-using-pip).

## Usage example

```python
# Import some basic classes
import sys
from p4_api_bridge import SwitchApiConfig, SwitchBase, ApiBridgeFactory, ApiBridge

# Import switch-specific classes
from p4_api_bridge import SimpleSwitchThriftApiConfig, NikssCtlApiConfig

# The factory is responsible for creating and cache API brides
api_factory = ApiBridgeFactory()


# A custom class that represents a P4 programmable switch
class MySwitch(SwitchBase):
    def __init__(self, name: str, config: SwitchApiConfig) -> None:
        super().__init__(name, config)

    @property
    def api(self) -> ApiBridge:
        return api_factory.get(self)


# Create switch objects, deciding the underlying API based on a command line argument
switches = []
if sys.argv[1] == 'thrift':
    switches.append(MySwitch('s1', SimpleSwitchThriftApiConfig(
            thrift_port=9090,
            interface_to_port={
                's1-eth0': 1,
                's1-eth1': 2,
            }
    )))
else:
    switches.append(MySwitch('s1', NikssCtlApiConfig(
            pipeline_id=42
    )))

# Use the API
for switch in switches:
    switch.api.table_clear('MyIngress.my_table')

    # s1-eth0 will automatically be translated to the numeric port identifier
    switch.api.table_add('MyIngress.my_table', ['10.1.1.2/24'], 'MyIngress.ip_forward', ['s1-eth0'])

    with switch.api.try_create_batch():
        # ...
        pass  # Execute multiple operations in a single batch, if the underlying API supports it

# Close the API bridge instances
api_factory.close()
```

The requirements of the various supported underlying control plane APIs can be found in the documentation
of the `XyzApiConfig` classes. The `SwitchApiConfig` class is the base class for all switch-specific API configurations.

More information about the library can be found in the documentation of the individual classes,
e.g. the `ApiBridge` class, which is the most important class in the library.
