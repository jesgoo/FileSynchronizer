#coding: UTF-8
__author__ = 'yangchenxing'
import collections
import os
import subprocess
import time

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
        if not event.is_directory and event.src_path.endswith('.md5'):
            log.info('探测到新增MD5文件: %s', event.src_path)
            self.synchronize(event.src_path)

    def synchronize(self, path=None):
        log.debug('同步文件: %s', path)
        if path:
            if path.endswith('.md5'):
                path = path[:-4]
            log.debug('修正文件路径: %s', path)
            if os.path.exists(path):
                log.debug('文件存在，开始同步')
                for file_sync_config in self._files_synchronizing_configs:
                    if file_sync_config.path == path:
                        self.synchronize_file(file_sync_config)
                self.synchronize()
        else:
            for directory_synchronizing_config in self._directory_synchronizing_configs:
                self.synchronize_directory(directory_synchronizing_config)

    def synchronize_file(self, config):
        log.debug('同步单文件: %s', config.local_path)
        processes = [(server, subprocess.Popen(['scp',
                                                config.local_path,
                                                '%s:%s' % (server, config.remote_path)]))
                                for server in ServerGroup.group(config.server_group)]
        running_processes = processes
        deadline = time.time() + self._files_synchronizing_timeout
        while 1:
            if time.time() >= deadline:
                break
            processes = running_processes
            running_processes = []
            for server, process in processes:
                return_code = process.poll()
                if return_code is None:
                    running_processes.append((server, process))
                elif return_code != 0:
                    log.error('同步文件失败: local_path=%s, server=%s, remote_path=%s, return_code=%d',
                              config.local_path, server, config.remote_path, return_code)
                else:
                    log.info('同步文件成功: local_path=%s, server=%s, remote_path=%s, return_code=%d',
                             config.local_path, server, config.remote_path, return_code)
        for server, process in running_processes:
            log.error('同步文件超时: local_path=%s, server=%s, remote_path=%s, timeout=%d',
                      config.local_path, server, config.remote_path, self._files_synchronizing_timeout)
            process.kill()

    def synchronize_directory(self, config):
        log.debug('同步目录: %s', self._path)
        for server in ServerGroup.group(config.server_group):
            print ['rsync', self._path, '%s:%s' % (server, config.remote_path)]
        processes = [(server, subprocess.Popen(['rsync',
                                                self._path,
                                                '%s:%s' % (server, config.remote_path)]))
                     for server in ServerGroup.group(config.server_group)]
        running_processes = processes
        deadline = time.time() + self._directory_synchronizing_timeout
        while 1:
            if time.time() >= deadline:
                break
            processes = running_processes
            running_processes = []
            for server, process in processes:
                return_code = process.poll()
                if return_code is None:
                    running_processes.append((server, process))
                elif return_code != 0:
                    log.error('同步文件夹失败: local_path=%s, server=%s, remote_path=%s, return_code=%d',
                              self._path, server, config.remote_path, return_code)
                else:
                    log.info('同步文件夹成功: local_path=%s, server=%s, remote_path=%s, return_code=%d',
                             self._path, server, config.remote_path, return_code)
            time.sleep(1)
        for server, process in running_processes:
            log.error('同步文件夹超时: local_path=%s, server=%s, remote_path=%s, timeout=%d',
                      self._path, server, config.remote_path, self._directory_synchronizing_timeout)
            process.kill()


class DirectoryMonitorApplication(jesgoo.application.Application):
    def __init__(self, *args, **kwargs):
        super(DirectoryMonitorApplication, self).__init__('..', *args, **kwargs)
        self._observer = watchdog.observers.Observer()

    def parse_args(self):
        parser = self._create_default_argument_parser('捷酷目录同步工具')
        return parser.parse_args()

    def main(self, args):
        super(DirectoryMonitorApplication, self).main(args)
        for server_group in self.config.directory_monitor.server_groups:
            ServerGroup.group(server_group.name).extend(server_group.servers)
        for directory_monitor_config in self.config.directory_monitor.directories:
            directory_monitor = DirectoryMonitor(**directory_monitor_config.as_config_dict)
            path = os.path.abspath(directory_monitor_config.path)
            print 'schedule', directory_monitor, path
            self._observer.schedule(directory_monitor, path)
            #self._observer.schedule(watchdog.events.LoggingEventHandler(), path, True)
        self._observer.start()
        self._observer.join()


if __name__ == '__main__':
    application = DirectoryMonitorApplication()
    application.run()
