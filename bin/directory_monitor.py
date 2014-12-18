#coding: UTF-8
__author__ = 'yangchenxing'
import argparse
import collections
import os
import sys

import gevent.event
import gevent.monkey
import gevent.subprocess
import watchdog.events
import watchdog.observers

import jesgoo.application
import jesgoo.supervisorutil.log as log


class ServerGroup(object):
    _GROUPS = collections.defaultdict(list)

    def __init__(self):
        pass

    @staticmethod
    def group(name):
        return ServerGroup._GROUPS[name]


class DirectoryMonitor(watchdog.events.FileSystemEventHandler):
    PushConfig = collections.namedtuple('PushConfig', ('local_path', 'remote_path', 'server_group'))

    def __init__(self, path, files_synchronizing=None, directory_synchronizing=None,
                 file_synchorinzing_timeout=5, directory_synchronizing_timeout=60):
        self._path = path
        self._files_synchronizing_configs = files_synchronizing if files_synchronizing else []
        self._directory_synchronizing_configs = directory_synchronizing if directory_synchronizing else []
        self._files_synchronizing_timeout = file_synchorinzing_timeout
        self._directory_synchronizing_timeout = directory_synchronizing_timeout

    def on_created(self, event):
        if event.is_directory and event.src_path.endswith('.md5'):
            self.synchronize(event.src_path)

    def synchronize(self, path=None):
        if path:
            if path.endswith('.md5'):
                path = path[:-4]
            if os.path.exists(path):
                for file_sync_config in self._files_synchronizing_configs:
                    if file_sync_config.path == path:
                        self.synchronize_file(file_sync_config)
        else:
            for directory_synchronizing_config in self._directory_synchronizing_configs:
                self.synchronize_directory(directory_synchronizing_config)

    def synchronize_file(self, config):
        for server, process in [(server, gevent.subprocess.Popen(['scp',
                                                                  self._path,
                                                                  '%s%s' % (server, config.remote_path)]))
                                for server in ServerGroup.group(config.server_group)]:
            return_code = process.wait(self._files_synchronizing_timeout)
            if return_code is None:
                log.error('同步文件超时: local_path=%s, server=%s, remote_path=%s, timeout=%d',
                          config.local_path, server, config.remote_path, self._files_synchronizing_timeout)
                process.kill()
            elif return_code != 0:
                log.error('同步文件失败: local_path=%s, server=%s, remote_path=%s, return_code=%d',
                          config.local_path, server, config.remote_path, return_code)

    def synchronize_directory(self, config):
        if self._directory_synchronizing_configs is None:
            return
        for server, process in [(server, gevent.subprocess.Popen(['rsync',
                                                                  config.local_path,
                                                                  '%s%s' % (server, config.remote_path)]))
                                for server in ServerGroup.group(config.server_group)]:
            return_code = process.wait(self._directory_synchronizing_timeout)
            if return_code is None:
                log.error('同步文件夹超时: local_path=%s, server=%s, remote_path=%s, timeout=%d',
                          config.local_path, server, config.remote_path, self._directory_synchronizing_timeout)
                process.kill()
            elif return_code != 0:
                log.error('同步文件夹是白: local_path=%s, server=%s, remote_path=%s, return_code=%d',
                          config.local_path, server, config.remote_path, return_code)


class DirectoryMonitorApplication(jesgoo.application.Application):
    def __init__(self, *args, **kwargs):
        super(DirectoryMonitorApplication, self).__init__('..', *args, **kwargs)
        self._observer = watchdog.observers.Observer()

    def parse_args(self):
        parser = self._create_default_argument_parser('捷酷目录同步工具')
        return parser.parse_args()

    def main(self, args):
        super(DirectoryMonitorApplication, self).main(args)
        for server_group in self.config.server_groups:
            ServerGroup.group(server_group.name).extend(server_group.servers)
        for directory_monitor_config in self.config.directory_monitor.directories:
            directory_monitor = DirectoryMonitor(**directory_monitor_config.as_config_dict)
            self._observer.schedule(directory_monitor, directory_monitor_config.path)
        self._observer.start()


if __name__ == '__main__':
    application = DirectoryMonitorApplication()
    application.run()
    gevent.event.Event().wait()