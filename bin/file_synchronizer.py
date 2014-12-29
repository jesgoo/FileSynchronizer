#coding: UTF-8
__author__ = 'yangchenxing'
import collections
import os
import subprocess
import time

import watchdog.events
import watchdog.observers

import jesgoo2.application

log = jesgoo2.application.log


server_groups = collections.defaultdict(list)


class DirectoryMonitor(watchdog.events.FileSystemEventHandler):
    def __init__(self, path, files_synchronizing=None, directory_synchronizing=None,
                 file_synchronizing_timeout=5, directory_synchronizing_timeout=60):
        self._path = os.path.abspath(path)
        self._files_synchronizing_configs = files_synchronizing if files_synchronizing else []
        self._directory_synchronizing_configs = directory_synchronizing if directory_synchronizing else []
        self._files_synchronizing_timeout = file_synchronizing_timeout
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
                    if os.path.join(self._path, file_synchronizing_config.path) == path:
                        self.synchronize_file(path, file_synchronizing_config.remote_path,
                                              file_synchronizing_config.server_group)
                for directory_synchronizing_config in self._directory_synchronizing_configs:
                    remote_path = os.path.join(directory_synchronizing_config.remote_path,
                                               os.path.relpath(path, self._path))
                    self.synchronize_file(path, remote_path, directory_synchronizing_config.server_group)
        else:
            log.info('全部同步')
            for file_synchronizing_config in self._files_synchronizing_configs:
                self.synchronize_file(os.path.join(self._path, file_synchronizing_config.path),
                                      file_synchronizing_config.remote_path,
                                      file_synchronizing_config.server_group)
            for directory_synchronizing_config in self._directory_synchronizing_configs:
                self.synchronize_file(self._path, directory_synchronizing_config.remote_path,
                                      directory_synchronizing_config.server_group)

    def synchronize_file(self, local_path, remote_path, server_group):
        log.debug('同步文件: %s', local_path)
        processes = [(server, subprocess.Popen(['rsync', '-r', '-T', '/tmp',
                                                local_path, '%s:%s' % (server, remote_path)]))
                     for server in server_groups[server_group]]
        running_process = processes
        deadline = time.time() + self._files_synchronizing_timeout
        while time.time() < deadline:
            time.sleep(1)
            processes = running_process
            running_process = []
            for server, process in processes:
                status = process.poll()
                if status is None:
                    running_process.append((server, process))
                elif status != 0:
                    log.error('同步失败: local_path=%s, server=%s, remote_path=%s, return_code=%d',
                              local_path, server, remote_path, status)
                else:
                    log.info('同步成功: local_path=%s, server=%s, remote_path=%s, return_code=%d',
                             local_path, server, remote_path, status)
            if not running_process:
                break
        for server, process in running_process:
            log.error('同步超时: local_path=%s, server=%s, remote_path=%s, timeout=%d',
                      local_path, server, remote_path, self._files_synchronizing_timeout)
            process.kill()


class DirectoryMonitorApplication(jesgoo2.application.StandaloneApplication):
    def __init__(self, *args, **kwargs):
        super(DirectoryMonitorApplication, self).__init__(*args, **kwargs)
        self._observer = watchdog.observers.Observer()

    def main(self):
        super(DirectoryMonitorApplication, self).main()
        for server_group in self.config.directory_monitor.server_groups:
            server_groups[server_group.name].extend(server_group.servers)
        for directory_monitor_config in self.config.directory_monitor.directories:
            directory_monitor = DirectoryMonitor(**directory_monitor_config.as_namespace_dict)
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
