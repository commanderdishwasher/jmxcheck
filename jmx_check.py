"""
JMX monitoring via Jolokia Java agent

Usage example: Checking kafka cluster members for underReplicatedPartitions

    import sys
    from jmx_check import JMXCheck, MBean

    if __name__ == '__main__':
        metric_name = 'kafka.server:type=ReplicaManager,name=UnderReplicatedPartitions'
        mbean1 = MBean(metric_name, jolokia_host='kafka1')
        mbean2 = MBean(metric_name, jolokia_host='kafka2')
        mbean3 = MBean(metric_name, jolokia_host='kafka3')
        mbean4 = MBean(metric_name, jolokia_host='kafka4')
        mbean5 = MBean(metric_name, jolokia_host='kafka5')

        warning_thresh = 1
        critical_thresh = 1
        warn_explanation = '''
            Please contact DBA team by mail.
            '''

        crit_explanation = '''
            Please contact DBA team by phone.
            '''
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

Throws exceptions:
    JolokiaInvalidResponse
    JolokiaConnectionError

Author: Roy Antman
Version: 0.1
Compatible: Python 2.7+, Python 3.5+
"""
from __future__ import print_function
import requests
import json
import argparse
import sys


class ProgramException(Exception):
    """Base class for UDE"""
    pass


class JolokiaInvalidResponse(ProgramException):
    """Raised when Jolokia returns a reponse we did not expect or with unknown format"""
    pass


class JolokiaConnectionError(ProgramException):
    """Raised when the program cannot connect to Jolokia"""
    pass


class MBeanResult(object):
    def __init__(self, mbean_name, content):
        self._mbean_name = mbean_name
        self._content = content
        self._value = None

    # Turning some attributes to be immutable
    @property
    def mbean_name(self):
        return self._mbean_name

    @property
    def content(self):
        return self._content

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, value):
        self._value = value

    def get_value_from_result(self, mbean_attribute, mbean_key):
        if mbean_key:
            return self.content[mbean_attribute][mbean_key]
        else:
            return self.content[mbean_attribute]


class MBean(object):
    def __init__(self, mbean_name, attribute='Value', key=None, jolokia_host='localhost', jolokia_port=8778, jolokia_context='jolokia',
                 jolokia_user=None, jolokia_pass=None):
        self._mbean_name = mbean_name
        self._attribute = attribute
        self._key = key

        self._jolokia_host = jolokia_host
        self._jolokia_port = jolokia_port
        self._jolokia_user = jolokia_user
        self._jolokia_pass = jolokia_pass
        self._jolokia_context = jolokia_context

        # Fix trailing slash
        if self._jolokia_context[-1] != "/":
            self._jolokia_context += "/"

    # Turning some attributes to be immutable
    @property
    def mbean_name(self):
        return self._mbean_name

    @property
    def attribute(self):
        return self._attribute

    @property
    def key(self):
        return self._key

    @property
    def jolokia_host(self):
        return self._jolokia_host

    @property
    def jolokia_port(self):
        return self._jolokia_port

    @property
    def jolokia_context(self):
        return self._jolokia_context

    @property
    def jolokia_user(self):
        return self._jolokia_user

    @property
    def jolokia_pass(self):
        return self._jolokia_pass

    def get_jmx_result(self):
        """
        Fetches the given metric from jolokia and returns as list of MBeanResult objects

        :return: list of MBeanResult objects [MBeanResult]
        """

        url = "{}read/{}".format("http://" + self.jolokia_host + ":" + str(self.jolokia_port) + "/" + self.jolokia_context, self.mbean_name)

        try:
            if self.jolokia_user and self.jolokia_pass:
                response = requests.get(url, auth=(self.jolokia_user, self.jolokia_pass), timeout=(5.0, 5.0))
            else:
                response = requests.get(url)

        except (requests.ConnectionError, requests.ConnectTimeout) as exception:
            raise JolokiaConnectionError(str(exception))
        assert response.status_code == 200
        metrics = json.loads(response.content.decode())

        # We got something unexpected from Jolokia
        if 'value' not in metrics:
            raise JolokiaInvalidResponse("Invalid response from Jolokia:\n" + str(metrics))

        metric_list = []
        # If we got a single metric we will have 'mbean' key
        if 'mbean' in metrics['request'].keys():
            mbean_result = MBeanResult(metrics['request']['mbean'], metrics['value'])
            metric_list.append(mbean_result)
        else:
            for metric, metric_value in metrics['value'].items():
                metric_list.append(MBeanResult(metric, metric_value))

        return metric_list


class JMXCheck(object):
    def __init__(self, warn_explanation='', crit_explanation=''):
        self.warn_explanation = warn_explanation
        self.crit_expalanation = crit_explanation

    @staticmethod
    def validate_result(mbean, warning_thresh, critical_thresh, compare=False, second_mbean=None, reverse=False):
        """
        :param mbean: MBean object
        :param second_mbean: A second MBean. If not None, it will calculate a percentage between the mbeans and treat the thresholds
               as percentages. (e.g warning_thresh=80 critical_thresh=90)
        :param warning_thresh: Threshold for warning (equals or greater). Can give an MBeanResult to make other mbean value as a threshold.
        :param critical_thresh: Treshold for critical (equals or greater). Can give an MBeanResult to make other mbean value as a threshold.
        :param compare: Exact match instead of ranges (Will convert everything to string)
        :param reverse: Reverse the logic of range validation
        :return: tuple(result_code, result_value)
                 result_code = 0-OK, 1-Warning, 2-Critical
        """

        return_code = 0

        # Adjust parameters for needed behavior.
        # Check if warning_threshold or critical_threshold are MBean objects, if so, retrieve their values and override the parameter
        if isinstance(warning_thresh, MBean):
            result = warning_thresh.get_jmx_result()
            if len(result) > 1:
                print("MONITORING ERROR - Warning threshold is MBean and does not return a single value")
                return 2, None

            if len(result) == 0:
                print("MONITORING ERROR - Warning threshold is MBean and does not return a value")
                return 2, None

            warning_thresh = result[0].get_value_from_result(warning_thresh.attribute, warning_thresh.key)

        if isinstance(critical_thresh, MBean):
            result = critical_thresh.get_jmx_result()
            if len(result) > 1:
                print("MONITORING ERROR - Critical threshold is MBean and does not return a single value")
                return 2, None

            if len(result) == 0:
                print("MONITORING ERROR - Critical threshold is MBean and does not return a value")
                return 2, None

            critical_thresh = result[0].get_value_from_result(critical_thresh.attribute, critical_thresh.key)

        # Get MBean result value
        mbean_value = mbean.get_jmx_result()[0].get_value_from_result(mbean.attribute, mbean.key)

        # Get second MBean result value and change mbean_value to a percentage result
        mbean_percent_factors = None
        if second_mbean:
            second_mbean_value = second_mbean.get_jmx_result()[0].get_value_from_result(second_mbean.attribute, second_mbean.key)
            mbean_percent_factors = "({}/{})".format(mbean_value, second_mbean_value)
            mbean_value = round((mbean_value / second_mbean_value) * 100)

        # Check for critical threshold first
        if (compare and str(mbean_value) == str(critical_thresh)) or \
                (not compare and not reverse and mbean_value >= float(critical_thresh)) or \
                (not compare and reverse and mbean_value <= float(critical_thresh)):
            return_code = 2
        elif (compare and str(mbean_value) == str(warning_thresh)) or \
                (not compare and not reverse and mbean_value >= float(warning_thresh)) or \
                (not compare and reverse and mbean_value <= float(warning_thresh)):
            return_code = 1

        if second_mbean:
            mbean_value = "{}% {}".format(str(mbean_value), mbean_percent_factors)

        return return_code, str(mbean_value)

    def check_metric(self, mbean, warning_thresh, critical_thresh, compare=False, print_result=True, second_mbean=None, reverse=False):
        return_code, return_value = JMXCheck.validate_result(mbean,
                                                             warning_thresh,
                                                             critical_thresh,
                                                             compare=compare,
                                                             second_mbean=second_mbean,
                                                             reverse=reverse)

        if print_result:
            return_classification = 'OK'

            if return_code == 1:
                return_classification = 'WARNING'
                explanation = self.warn_explanation
            elif return_code == 2:
                return_classification = 'CRITICAL'
                explanation = self.crit_expalanation
            else:
                explanation = ''

            if mbean.key:
                print("{} - {} A:{} K:{} : {}".format(return_classification, mbean.mbean_name, mbean.attribute, mbean.key, str(return_value)))
            else:
                print("{} - {} A:{} : {}".format(return_classification, mbean.mbean_name, mbean.attribute, str(return_value)))

            if explanation:
                print("{}\n".format(explanation))

        return return_code

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='JMX monitoring via Jolokia Java agent')
    parser.add_argument('--mbean', help='MBean path', required=True, metavar='MBEAN_FULL_PATH')
    parser.add_argument('--mbean-attribute', default='Value', help='MBean attirbute to inspect', metavar='ATRIBUTE_NAME')
    parser.add_argument('--mbean-key', default=None, help='MBean attribute key to inspect', metavar='KEY_NAME')
    parser.add_argument('--second-mbean', help='Second MBean path', required=False, metavar='SECOND_MBEAN_FULL_PATH')
    parser.add_argument('--second-mbean-attribute', help='Second MBean attribute', required=False, default='Value', metavar='ATTRIBUTE_NAME')
    parser.add_argument('--second-mbean-key', help='Second MBean key', required=False, default=None, metavar='KET_NAME')
    parser.add_argument('--warning', help='Warning threshold', required=True, metavar='WARNING_THRESHOLD')
    parser.add_argument('--critical', help='Critical threshold', required=True, metavar='CRITICAL_THRESHOLD')
    parser.add_argument('--jolokia-host', default='localhost', help='Jolokia agent host', metavar='JOLOKIA_HOST')
    parser.add_argument('--jolokia-port', type=int, default=8778, help='Jolokia agent port', metavar='JOLOKIA_PORT')
    parser.add_argument('--jolokia-context', default='jolokia', help='Jolokia context', metavar='JOLOKIA_CONTEXT')
    parser.add_argument('--compare', default=False, action='store_true', help='Compare check instead of range check')
    parser.add_argument('--reverse', default=False, action='store_true', help='Reverse threshold comparison to be descending')
    args = parser.parse_args()

    mbean_obj = MBean(args.mbean, attribute=args.mbean_attribute, key=args.mbean_key, jolokia_host=args.jolokia_host, jolokia_port=args.jolokia_port,
                      jolokia_context=args.jolokia_context)

    if args.second_mbean and args.second_mbean_attribute and args.second_mbean_key:
        second_mbean_obj = MBean(args.second_mbean, attribute=args.second_mbean_attribute, key=args.second_mbean_key, jolokia_host=args.jolokia_host,
                                 jolokia_port=args.jolokia_port, jolokia_context=args.jolokia_context)
    else:
        second_mbean_obj = None

    jmx_check = JMXCheck(warn_explanation='Warning explanation', crit_explanation='Critical explanation')
    sys.exit(jmx_check.check_metric(mbean_obj,
                                    args.warning,
                                    args.critical,
                                    compare=args.compare,
                                    reverse=args.reverse, second_mbean=args.second_mbean))
