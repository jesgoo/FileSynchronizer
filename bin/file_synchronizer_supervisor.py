#!/usr/bin/env python
#coding: UTF-8
import os
import sys

import jesgoo.notification
import jesgoo.supervisorutil.log_watcher
import jesgoo.supervisorutil.supervisor_control
import jesgoo.supervisorutil.log


notification_service = jesgoo.notification.NotificationService(host='192.168.0.101', port=8080)
working_directory = os.path.abspath(os.path.join(os.path.dirname(sys.argv[0]), os.path.pardir))


app_config = {
    'workdir': working_directory,
    'programs': [
        {
            'command': 'python bin/directory_monitor.py start',
            'process_name': 'directory_monitor',
            'autorestart': True,
            'stderr_logfile': 'None',
            'stderr_events_enabled': True,
        },
    ],
    'eventlistener': {
        'stdout_logfile': 'None',
        'handlers': [
            {
                'event_names': ['PROCESS_STATE_EXITED'],
                'notifier': notification_service.simple_mail_notifier(
                    receivers=['rd@jesgoo.com'],
                ),
                'subject': '联盟服务进程%(processname)s异常退出',
                'message': '',
                'debug': False,
            },
            {
                'event_names': ['PROCESS_LOG_STDERR'],
                'notifier': jesgoo.supervisorutil.log.LogSpliterNotifier(
                    os.path.join(working_directory, 'conf', 'config.yaml')),
                'subject': '',
                'message': '%(data)s',
                'debug': False,
            }
        ],
        'debug': False,
    }
}


jesgoo.supervisorutil.supervisor_control.main(app_config)
