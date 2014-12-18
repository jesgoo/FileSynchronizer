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

    @staticmethod
    def localhost_group():
        group = ServerGroup.group('localhost')
        if not group:
            group.extend([
                'localhost',
                '127.0.0.1'
            ])
        return group

    @staticmethod
    def is_localhost(server):
        return server in ('127.0.0.1', 'localhost') or server in ServerGroup.localhost_group()


class DirectoryMonitor(watchdog.events.FileSystemEventHandler):
    PushConfig = collections.namedtuple('PushConfig', ('local_path', 'remote_path', 'server_group'))

    def __init__(self, path, files_synchronizing=None, directory_synchronizing=None,
                 file_synchorinzing_timeout=5, directory_synchronizing_timeout=60):
        self._path = os.path.abspath(path)
        self._files_synchronizing_configs = files_synchronizing if files_synchronizing else []
        self._directory_synchronizing_configs = directory_synchronizing if directory_synchronizing else []
        self._files_synchronizing_timeout = file_synchorinzing_timeout
        self._directory_synchronizing_timeout = directory_synchronizing_timeout

    def on_created(self, event):
        if not event.is_directory:
            self.synchronize(event.src_path)

    def on_modified(self, event):
        if not event.is_directory:
            self.synchronize(event.src_path)

    def synchronize(self, path=None):
        if path:
            path = os.path.abspath(path)
            log.info('同步文件: %s', path)
            if os.path.exists(path):
                log.debug('文件存在，开始同步')
                for file_synchronizing_config in self._files_synchronizing_configs:
                    if file_synchronizing_config.path == path:
                        self.synchronize_file(path, file_synchronizing_config.remote_path,
                                              file_synchronizing_config.server_group)
                for directory_synchronizing_config in self._directory_synchronizing_configs:
                    remote_path = os.path.join(directory_synchronizing_config.remote_path,
                                               os.path.relpath(path, self._path))
                    self.synchronize_file(path, remote_path, directory_synchronizing_config.server_group)
        else:
            log.info('全部同步')
            for file_synchronizing_config in self._files_synchronizing_configs:
                self.synchronize_file(path, file_synchronizing_config.remote_path,
                                      file_synchronizing_config.server_group)
            for directory_synchronizing_config in self._directory_synchronizing_configs:
                self.synchronize_directory(directory_synchronizing_config)

    def synchronize_file(self, local_path, remote_path, server_group):
        log.debug('同步单文件: %s', local_path)
        processes = [(server,
                      subprocess.Popen(['scp', local_path, '%s:%s' % (server, remote_path)])
                      if not ServerGroup.is_localhost(server) else
                      subprocess.Popen(['cp', local_path, remote_path]))
                     for server in ServerGroup.group(server_group)]
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
                              local_path, server, remote_path, return_code)
                else:
                    log.info('同步文件成功: local_path=%s, server=%s, remote_path=%s, return_code=%d',
                             local_path, server, remote_path, return_code)
            if not running_processes:
                break
            time.sleep(1)
        for server, process in running_processes:
            log.error('同步文件超时: local_path=%s, server=%s, remote_path=%s, timeout=%d',
                      local_path, server, remote_path, self._files_synchronizing_timeout)
            process.kill()

    def synchronize_directory(self, config):
        log.debug('同步目录: %s', self._path)
        processes = [(server,
                      subprocess.Popen(['rsync', '-r', self._path, '%s:%s' % (server, config.remote_path)])
                      if not ServerGroup.is_localhost(server) else
                      subprocess.Popen('cp %s %s/' % (os.path.join(self._path, '*'), config.remote_path), shell=True))
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
            if not running_processes:
                break
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
            self._observer.schedule(directory_monitor, path)
            directory_monitor.synchronize()
        self._observer.start()
        try:
            while 1:
                time.sleep(1)
        except KeyboardInterrupt:
            self._observer.stop()
        except SystemExit:
            self._observer.stop()
        self._observer.join()


if __name__ == '__main__':
    application = DirectoryMonitorApplication()
    application.run()
