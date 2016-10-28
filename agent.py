#!/usr/bin/python
#encoding=utf-8

import thread
import socket
import select, errno
import sys
from common import Log as Log
from multiprocessing import Process,Queue,Pool, Manager, Value, Array
import pdb 
import multiprocessing
import time
import common
import Queue
import signal

class Heart(object):
    def __init__(self):
        self.start = int(time.time())
        self.count = 0

    def reset(self):
        self.count = 0

    def HeartHandle(self):
        while True:
            now = int(time.time())
            if now - self.start > 10:
                self.start = now
                self.count = self.count + 1
            else:
				time.sleep(3)

class Epoll(object):
    def __init__(self):
        self.fileno_to_connection = {}
        self.heart = {}
        self.send_msg = {}

    def bind_and_connect(self):
        try:
            self.fd = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
        except socket.error, msg:
            Log.error("create socket failed")
            sys.exit(0)

        try:
            self.fd.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        except socket.error, msg:
            Log.error("setsocketopt SO_REUSEADDR failed")
            sys.exit(0)

        try:
            self.fd.bind((g_val.Ip, int(g_val.MyPort)))
        except socket.error, msg:
            Log.error("bind:%s failed" % g_val.MyPort)
            sys.exit(0)

        try:
            self.fd.connect((g_val.ServerIp,9999))
            self.fd.setblocking(0)
            self.fileno_to_connection[self.fd.fileno()] = self.fd
            self.heart[self.fd.fileno()] = Heart()
        except socket.error, msg:
            Log.error("connect %s:9999 failed" % g_val.ServerIp)
            sys.exit(0)
        
        try:
            self.epoll_fd = select.epoll()
            self.epoll_fd.register(self.fd.fileno(), select.EPOLLIN)
        except select.error, msg:
            Log.error(msg)
            sys.exit(0)

    def Modify(self):
        while True:
            for key, value in self.heart.items():
                if value.count > 5:
                    self.epoll_fd.modify(key, select.EPOLLET | select.EPOLLHUP)
            if not send.empty():
                self.epoll_fd.modify(self.fd.fileno(), select.EPOLLET | select.EPOLLOUT)
            else:
                time.sleep(1) 

    def HeartBeat(self):
       run_list = []
       while True:
           for id in run_list:
              if id not in self.heart.key():
                  run_list.remove(id)
           for key, value in self.heart.items():
               if key not in run_list:
                   run_list.append(key)
                   value.HeartHandle()
           time.sleep(1)

    def hanle_event(self):
        Log.info("wait msg")
        thread.start_new_thread(Epoll.Modify, (self, ))
        thread.start_new_thread(Epoll.HeartBeat, (self, ))
        while True:
            if g_val.ExitFlag.value == 1:
                Log.info("HandleMsg exit") 
                sys.exit(0)
            epoll_list = self.epoll_fd.poll()
            for fd, events in epoll_list:
                if select.EPOLLIN & events:
                    datas = ''
                    while True:
                        try:
                            data = self.fileno_to_connection[fd].recv(10)
                            if not data and not datas:
                                self.epoll_fd.unregister(fd)
                                self.fileno_to_connection[fd].close()
                                break
                            else:
                                datas += data
                        except socket.error, msg:
                            if msg.errno == errno.EAGAIN:
                                Log.debug("fd:%s receive %s" % (fd, datas)) #  ggg:ceph -s
                                self.heart[fd].reset()
                                recv_msg = datas.split("|")
                                if recv_msg[1] == "Notify":
                                    if g_val.NotifyFlag.value == 0:
                                        g_val.NotifyFlag.value = 1 
                                    else:
                                        g_val.NotifyFlag.value = 0
                                    output = "Nofify Mode set success"
                                elif recv_msg[1] == "heart echo":
                                    Log.info("recv heart echo from server")
                                    break
                                else:
                                    status, output = common.sh_cmd(recv_msg[1])
                                if output != "":
                                    send.put(recv_msg[0]+ "@" + output)
                                    self.epoll_fd.modify(fd, select.EPOLLET | select.EPOLLOUT)
                                break
                            else:
                                self.epoll_fd.unregister(fd)
                                self.fileno_to_connection[fd].close()
                                Log.error(msg)
                                break
                    break 
                elif select.EPOLLHUP & events:
                    self.epoll_fd.unregister(fd)
                    self.fileno_to_connection[fd].close()
                    Epoll.bind_and_connect()
                elif select.EPOLLOUT & events:
                    while True:
                        if not send.empty():
                            self.fileno_to_connection[fd].sendall(send.get())
                        else:
                            break 

                    self.epoll_fd.modify(fd, select.EPOLLIN | select.EPOLLET)
                    break 
                else:
                    time.sleep(1)
                    break

def handle(signum, stack_frame):
    if g_val.NotifyFlag.value:
        status, output = common.sh_cmd("ceph health detail")
        if output != "HEALTH_OK":
            status, msg = common.sh_cmd("ceph -s")
            send.put(msg)
    signal.alarm(300)

def NotifyMode():
    Log.debug("enter notify success")
    signal.signal(signal.SIGALRM, handle)
    signal.alarm(300)
    while True:
        if g_val.ExitFlag.value == 1:
            Log.info("NotifyMode exit")
            sys.exit(0)
        time.sleep(30) #(60)
        send.put("heart beat")

def HandleMsg():
    ep = Epoll()
    ep.bind_and_connect()
    ep.hanle_event()

def SigHandler(signum, stack_frame):
    g_val.ExitFlag.value = 1

if __name__ == "__main__":
    g_val = common.Agent()
    recv = multiprocessing.Queue()
    send = multiprocessing.Queue()
    pw = multiprocessing.Process(target=HandleMsg)
    pr = multiprocessing.Process(target=NotifyMode)
    pw.start()
    pr.start()
    signal.signal(signal.SIGINT, SigHandler)
    if not pw.is_alive() and not pr.is_alive():
        Log.info("main process exit")
        sys.exit(0)
    #pw.join()
    #pr.join()