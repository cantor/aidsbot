#!/usr/bin/env python
# -*- coding: utf-8 -*-

'''

aidsbot - A simple irc bot library for python
Copyright (C) 2011 Adam Hose <adis@blad.is> and Elis Axelsson <etu AT elis DOT nu>

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA

'''

import socket
import ssl
import thread
import time
import threading

class aidsbot ():
    '''Handle IRC connections'''
    
    def __init__(self, botname, network, port, debug = False):
        self.network = network
        self.port    = port
        self.ssl     = False
        self.botname = botname
        self.debug   = debug
        self.run     = True
        self.privmsghandler = {}
        self.chanophandler  = {}
        self.chanlist= []
        self.failed  = False
        self.password = ''
        self.topics = {}
    
    def connect(self):
        '''Connect'''
        s = socket.socket()
        if self.ssl:
            self.socket = ssl.wrap_socket(s, cert_reqs=ssl.CERT_NONE, ssl_version=ssl.PROTOCOL_SSLv3)
        else:
            self.socket = s
        
        self.socket.connect((self.network, self.port))
        if self.password != '':
            self.send('PASS %s' % (self.password))
        self.send('NICK %s' % (self.botname), True)
        self.send('USER %s %s bla :%s' % (self.botname, self.network, self.botname), True)
        try: self.postconnect(self)
        except: pass
        self.failed = False
    
    def send(self, command, override = False):
        '''Send a raw command to the socket'''
        
        # Follow RFC 1459, do not send more than 512B
        command=str(command)
        if len(command) > 510:
            raise Exception('IRCError')
        
        # Dont try to send if network has failed
        if not self.failed or override:
            self.socket.send('%s\r\n' % command)
        
        else:
            return None
    
    def join(self, channel, addlist = True):
        '''Join channel'''
        if addlist:
            self.chanlist.append(channel)
        return self.send('JOIN :%s' % channel)
    
    def oper(self, user, password):
        '''Authenticate as IRC operator'''
        return self.send('OPER %s %s' % (user, password))
    
    def part(self, channel):
        '''Part a channel'''
        try: self.chanlist.remove(channel)
        except: pass
        
        return self.send('PART %s' % channel)
    
    def topic(self, channel, topic=None):
        '''Set/get topic for channel'''
        if topic == None:
            try:
                timestamp=self.topics[channel][1]
            except KeyError:
                timestamp=time.time()
                self.topics[channel]=(None,timestamp)
            
            self.send('TOPIC %s' % (channel))
            
            while self.topics[channel][1] == timestamp:
                time.sleep(0.01)
            
            return(self.topics[channel][0])
        else:
            self.send('TOPIC %s %s' % (channel, topic))
    
    def invite(self, nickname, channel):
        '''Invite user for channel'''
        return self.send('INVITE %s %s' % (nickname, channel))
    
    def notice(self, target, message):
        '''Send a notice to target'''
        return self.send('NOTICE %s :%s' % (target, message))
    
    def privmsg(self, target, message):
        '''Send message to target'''
        return self.send('PRIVMSG %s :%s' % (target, message))
    
    def mode(self, mode, channel = '', user = ''):
        '''
        Change user/channel modes on target
        user or channel is mandatory
        '''
        
        # Check args
        if user == '' and channel == '':
            return False
        
        return self.send('MODE %s %s %s' % (channel, mode, user))
    
    def kick(self, channel, user, reason = ''):
        '''Kick user from channel for reason'''
        return self.send('KICK %s %s :%s' % (channel, user, reason))
    
    def stop(self):
        '''Stop'''
        self.run = False
        self.send('QUIT')
        self.socket.close()
    
    def privmsghandler_add(self, command, function):
        '''Add function as handler for trigger'''
        command = ':' + command
        self.privmsghandler[command]=function
    
    def chanophandler_add(self, chanop, function):
        '''Add function as handler for channel operation'''
        self.chanophandler[chanop] = function
    
    def privmsg_split(self, data):
        '''Split data for easy usage'''
        data = data.split()
        user_info = data[0]
        msg_type = data[1]
        channel = data[2]
        message = data[3]
        for i in range(4, len(data)):
            message = message + ' ' + data[i]
        return user_info, msg_type, channel, message        
    
    def user_split(self, data):
        '''Split the user-data'''
        nick, rest = data.split('!')
        nick=nick.replace(':', '', 1)
        real_user=rest.split('@')[0]
        host=rest.split('@')[1]
        return nick, real_user, host
    
    def listen(self):
        '''Start listener in thread'''
        thread.start_new_thread(self.__listener, ())
    
    def __listener(self):
        '''Listener, listens the socket and sends complete commands to the handler'''
        save = ''
        
        while self.run:
            data = self.socket.recv(4096) # Reading Socket
            
            # Splitting at end of command
            for line in data.split('\n'):
                save = save + line # Store parts
                
                # Send completed commands to the handler
                if line.endswith('\r'):
                    self.__handler(save)
                    save = ''
    
    def __handler(self, line):
        data = line.strip()
        
        if len(data) < 1: return True # Drop empty lines
        
        if data.startswith('PING'):
            self.send(data.replace('PING', 'PONG'))
        
        # Handle user commands
        user_input = data.split()
        try:
            chanop = user_input[1]
        except IndexError:
            chanop = 'FAIL' # Network failed
        
        # Try custom chanop handlers
        try: thread.start_new_thread(self.chanophandler[chanop], (self, data))
        except: pass
        
        # Try custom triggers
        if chanop == 'PRIVMSG':
            triggers = user_input[3]
            try: thread.start_new_thread(self.privmsghandler[triggers], (self, data))
            except KeyError: pass
        
        # Static handling methods
        elif chanop == 'TOPIC': # We recived a topic update
            topic = data.split('TOPIC ', 1)[1].strip().split(' :', 1)
            self.topics[topic[0]] = topic[1]
        
        elif chanop == '332': # We recived a topic update
            topic = data.split(self.botname, 1)[1].strip().split(' :', 1)
            self.topics[topic[0]] = topic[1]
        
        # Reconnect on failure
        elif chanop == 'FAIL':
            self.failed = True
            while self.failed:
                time.sleep(5)
                try:
                    self.connect()
                except socket.error:
                    self.failed = True
            
            for chan in self.chanlist:
                self.join(chan, False)
        
        # Debug messages
        if self.debug == True:
            print(data)

