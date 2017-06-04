# JMXCheck - JMX Metrics Checker (Dependent on Jolokia java agent)

JMXCheck is a utility project that provides an easy to use interface for validating JMX MBean metrics.
The project was meant to be used as a Nagios plugin in mind (by providing a commandline interface) but can also
be used to create monitoring scripts in a matter of minutes.

Main features:
* Single MBean check with warning and critical thresholds
* Correlation check between two MBeans (will treat thresholds as percentage. e.g. max memory MBean vs used memory MBean)
* Reverse logic support
* Allows other MBeans to be used as thresholds and thus creating relations between MBeans.

Supports:
* Python 2.7+
* Python 3.5+

Dependencies:
* Python [requests] package
* [Jolokia] as java agent loaded into the JVM  

## Installation
All you need is to install the requirements using pip, and have JMXCheck.py in your working dir or PYTHONPATH.

```bash
pip install -r requirements.txt
```

## Usage (CLI)

```text
usage: jmx_check.py [-h] 
                    --mbean MBEAN_FULL_PATH
                    [--mbean-attribute ATRIBUTE_NAME] 
                    [--mbean-key KEY_NAME]
                    [--second-mbean SECOND_MBEAN_FULL_PATH]
                    [--second-mbean-attribute ATTRIBUTE_NAME]
                    [--second-mbean-key KET_NAME] 
                    --warning WARNING_THRESHOLD
                    --critical CRITICAL_THRESHOLD
                    [--jolokia-host JOLOKIA_HOST]
                    [--jolokia-port JOLOKIA_PORT]
                    [--jolokia-context JOLOKIA_CONTEXT] 
                    [--compare]
                    [--reverse]

JMX monitoring via Jolokia Java agent

optional arguments:
  -h, --help            show this help message and exit
  --mbean MBEAN_FULL_PATH
                        MBean path (Object Name)
  --mbean-attribute ATRIBUTE_NAME
                        MBean attirbute to inspect (Default: Value)
  --mbean-key KEY_NAME  MBean attribute key to inspect (Default: None)
  --second-mbean SECOND_MBEAN_FULL_PATH
                        Second MBean path (Object Name)
  --second-mbean-attribute ATTRIBUTE_NAME
                        Second MBean attribute (Default: Value)
  --second-mbean-key KET_NAME
                        Second MBean key (Default: None)
  --warning WARNING_THRESHOLD
                        Warning threshold
  --critical CRITICAL_THRESHOLD
                        Critical threshold
  --jolokia-host JOLOKIA_HOST
                        Jolokia agent host (Default: localhost)
  --jolokia-port JOLOKIA_PORT
                        Jolokia agent port (Default: 8778)
  --jolokia-context JOLOKIA_CONTEXT
                        Jolokia context (Default: jolokia)
  --compare             Compare check instead of range check (Default: False)
  --reverse             Reverse threshold comparison to be descending (Default: False)
```

Example: Checking Kafka UnderReplicatedPartitions, Warning:1, Critical:1
```bash
./jmx_check.py --mbean "kafka.server:type=ReplicaManager,name=UnderReplicatedPartitions" --warning 1 --critical 1
```

## Usage (API)

Example 1: Testing Kafka UnderReplicatedPartitions against all cluster brokers

```python
import sys
from jmx_check import JMXCheck, MBean, JolokiaConnectionError, JolokiaInvalidResponse

if __name__ == '__main__':
    metric_name = 'kafka.server:type=ReplicaManager,name=UnderReplicatedPartitions'
    mbean1 = MBean(metric_name, jolokia_host='kafka1')
    mbean2 = MBean(metric_name, jolokia_host='kafka2')
    mbean3 = MBean(metric_name, jolokia_host='kafka3')
    mbean4 = MBean(metric_name, jolokia_host='kafka4')
    mbean5 = MBean(metric_name, jolokia_host='kafka5')

    warning_thresh = 1
    critical_thresh = 1
    warn_explanation = """
        Please contact by mail.
        """

    crit_explanation = """
        Please contact by phone.
        """
    try:
        jmx_check = JMXCheck(warn_explanation=warn_explanation, crit_explanation=crit_explanation)
        sys.exit(max(jmx_check.check_metric(mbean1, warning_thresh, critical_thresh),
                     jmx_check.check_metric(mbean2, warning_thresh, critical_thresh),
                     jmx_check.check_metric(mbean3, warning_thresh, critical_thresh),
                     jmx_check.check_metric(mbean4, warning_thresh, critical_thresh),
                     jmx_check.check_metric(mbean5, warning_thresh, critical_thresh)))
    except (JolokiaConnectionError, JolokiaInvalidResponse) as jolokia_exception:
        print(jolokia_exception)
        sys.exit(2)
```

Example 2: Testing heap memory usage as percentage.
```python
import sys
from jmx_check import JMXCheck, MBean

if __name__ == '__main__':
    mbean = MBean('java.lang:type=Memory',
                  attribute='HeapMemoryUsage',
                  key='used',
                  jolokia_host='kafka')

    second_mbean = MBean('java.lang:type=Memory',
                         attribute='HeapMemoryUsage',
                         key='max',
                         jolokia_host='kafka')

    warning_thresh = 80
    critical_thresh = 90
    warn_explanation = """
        Please contact by mail.
        """

    crit_explanation = """
        Please contact by phone if alert is over 10 minutes.
        """
        
    jmx_check = JMXCheck(warn_explanation=warn_explanation, crit_explanation=crit_explanation)
    sys.exit(jmx_check.check_metric(mbean, warning_thresh, critical_thresh, second_mbean=second_mbean))
```

[jolokia]:https://jolokia.org/
[requests]:https://pypi.python.org/pypi/requests
