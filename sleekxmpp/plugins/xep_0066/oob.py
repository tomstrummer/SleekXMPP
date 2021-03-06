"""
    SleekXMPP: The Sleek XMPP Library
    Copyright (C) 2011 Nathanael C. Fritz, Lance J.T. Stout
    This file is part of SleekXMPP.

    See the file LICENSE for copying permission.
"""

import logging
import os

from sleekxmpp.stanza import Message, Presence, Iq
from sleekxmpp.exceptions import XMPPError
from sleekxmpp.xmlstream import register_stanza_plugin
from sleekxmpp.xmlstream.handler import Callback
from sleekxmpp.xmlstream.matcher import StanzaPath
from sleekxmpp.plugins.xep_0066 import stanza
import sleekxmpp.plugins.xep_0096 as xep_0096


log = logging.getLogger(__name__)


class XEP_0066(xep_0096.FileTransferProtocol):
    XMLNS = 'jabber:iq:oob'
    

    """
    XEP-0066: Out of Band Data

    Out of Band Data is a basic method for transferring files between
    XMPP agents. The URL of the resource in question is sent to the receiving
    entity, which then downloads the resource before responding to the OOB
    request. OOB is also used as a generic means to transmit URLs in other
    stanzas to indicate where to find additional information.

    Also see <http://www.xmpp.org/extensions/xep-0066.html>.

    Events:
        oob_transfer -- Raised when a request to download a resource
                        has been received.

    Methods:
        send_oob -- Send a request to another entity to download a file
                    or other addressable resource.
    """

    name = 'xep_0066'
    description = 'XEP-0066: Out of Band Data'
    dependencies = set(['xep_0030'])
    stanza.OOB.namespacestanza = stanza

    def plugin_init(self):
        """Start the XEP-0066 plugin."""

        self.url_handlers = {'global': self._default_handler,
                             'jid': {}}
        
        self.streamSessions = []

        register_stanza_plugin(Iq, stanza.OOBTransfer)
        register_stanza_plugin(Message, stanza.OOB)
        register_stanza_plugin(Presence, stanza.OOB)

        self.xmpp.register_handler(
                Callback('OOB Transfer',
                         StanzaPath('iq@type=set/oob_transfer'),
                         self._handle_transfer))
        self.xmpp.register_handler(
                Callback('OOB Transfer',
                         StanzaPath('iq@type=result/oob_transfer'),
                         self._handle_finished))
        self.xmpp.register_handler(
                Callback('OOB Transfer',
                         StanzaPath('iq@type=error/oob_transfer'),
                         self._handle_finished))
        
        self.register_url_handler(handler=self._download_file)

    def post_init(self):
        xep_0096.FileTransferProtocol.post_init(self)
        if self.xmpp.plugin.get('xep_0030'):
            self.xmpp.plugin['xep_0030'].add_feature(stanza.OOBTransfer.namespace)
            self.xmpp.plugin['xep_0030'].add_feature(stanza.OOB.namespace)
            
            
    def sendFile(self, fileName, to, threaded=True, sid=None, **kwargs):
        logging.debug("About to send file: %s via oob" %fileName)
        if not os.path.isfile(fileName):
            raise IOError('file: %s not found' %fileName)
        
        if self.xmpp.fulljid == to:
            raise Exception('Error setting up the stream, can not send file to ourselves %s', self.xmpp.fulljid)
        
        if not self.xmpp.state.ensure('connected'):
            raise Exception('Not connected to a server!')
        
        if sid is None:
            sid = xep_0096.generateSid()
            
        iq = self.send_oob(to, kwargs["url"])
        self.streamSessions[iq["id"]] = {"iq":iq["id"], "url":kwargs["url"], "sid":sid}
    
    def getSessionStatus(self, sid):
        '''
        Returns the status of the transfer specified by the sid.  If the session
        is not found none will be returned.
        '''
        return_session = None
        for session in self.streamSessions.items():
            if session["sid"] == sid:
                return_session = session
                break
        return return_session
    
    def getSessionStatusAll(self):
        return self.streamSessions.values()
    
    def cancelSend(self, sid): 
        '''
        You can't really cancel an oob file transfter after you send the request....
        Simply passing for now.
        '''
        pass        
    
    def register_url_handler(self, jid=None, handler=None):
        """
        Register a handler to process download requests, either for all
        JIDs or a single JID.

        Arguments:
            jid     -- If None, then set the handler as a global default.
            handler -- If None, then remove the existing handler for the
                       given JID, or reset the global handler if the JID
                       is None.
        """
        if jid is None:
            if handler is not None:
                self.url_handlers['global'] = handler
            else:
                self.url_handlers['global'] = self._default_handler
        else:
            if handler is not None:
                self.url_handlers['jid'][jid] = handler
            else:
                del self.url_handlers['jid'][jid]

    def send_oob(self, to, url, desc=None, ifrom=None, **iqargs):
        """
        Initiate a basic file transfer by sending the URL of
        a file or other resource.

        Arguments:
            url      -- The URL of the resource to transfer.
            desc     -- An optional human readable description of the item
                        that is to be transferred.
            ifrom    -- Specifiy the sender's JID.
            block    -- If true, block and wait for the stanzas' reply.
            timeout  -- The time in seconds to block while waiting for
                        a reply. If None, then wait indefinitely.
            callback -- Optional callback to execute when a reply is
                        received instead of blocking and waiting for
                        the reply.
        """
        iq = self.xmpp.Iq()
        iq['type'] = 'set'
        iq['to'] = to
        iq['from'] = ifrom
        iq['oob_transfer']['url'] = url
        iq['oob_transfer']['desc'] = desc
        return iq.send(False)

    def _run_url_handler(self, iq):
        """
        Execute the appropriate handler for a transfer request.

        Arguments:
            iq -- The Iq stanza containing the OOB transfer request.
        """
        if iq['to'] in self.url_handlers['jid']:
            return self.url_handlers['jid'][iq['to']](iq)
        else:
            if self.url_handlers['global']:
                self.url_handlers['global'](iq)
            else:
                raise XMPPError('service-unavailable')

    def _default_handler(self, iq):
        """
        As a safe default, don't actually download files.

        Register a new handler using self.register_url_handler to
        screen requests and download files.

        Arguments:
            iq -- The Iq stanza containing the OOB transfer request.
        """
        raise XMPPError('service-unavailable')

    def _handle_transfer(self, iq):
        """
        Handle receiving an out-of-band transfer request.

        Arguments:
            iq -- An Iq stanza containing an OOB transfer request.
        """
        log.debug('Received out-of-band data request for %s from %s:' % (
            iq['oob_transfer']['url'], iq['from']))
        self._run_url_handler(iq)
        iq.reply().send()
        
    def _handle_finished(self, iq):
        """
        Handle receiving an out-of-band transfer request.

        Arguments:
            iq -- An Iq stanza containing an OOB transfer request.
        """
        log.debug('Received out-of-band data result for %s from %s:' % (
            iq['oob_transfer']['url'], iq['from']))
        found_sid = self.streamSessions[iq["id"]]
        
        if found_sid is not None:
            del self.streamSessions[iq["id"]]
            if iq["type"].lower == "error":
                self.fileFinishedSending(found_sid, False)
            elif  iq["type"].lower == "result":
                self.fileFinishedSending(found_sid, True)
             
    def _download_file(self, iq):
        '''
        Download the file and notify xep-0096 we are finished.
        '''  
        #Check to see if the file transfer should be accepted
        acceptTransfer = False
        if self.acceptTransferCallback:
            acceptTransfer = self.acceptTransferCallback(sid=iq['query']['sid'])
        else:
            acceptTransfer = False
                
        #Ask where to save the file if the callback is present
        saveFileAs = "/dev/null"
        if self.fileNameCallback:
            saveFileAs = self.fileNameCallback(sid=iq['query']['sid'])
            
        #Do not accept a transfer from ourselves
        if self.xmpp.fulljid == iq['from']:
            acceptTransfer = False
        
        if acceptTransfer:
            self.streamSessions[iq["id"]] = {"iq":iq["id"], "url":iq['query']['url'], "sid":iq['query']['sid']}
            
            #TODO write code to download the file
            
            #send the result iq to let the initiator know this client has finished the download
            iq = self.xmpp.makeIqResult(id=iq["id"])
            iq['to'] = iq["from"]
            iq.send(block=False)
            
            #Now that we have the file notify xep_0096 so it can run the checksums.
            del self.streamSessions[iq["id"]]
            self.fileFinishedReceiving(self.streamSessions[iq["id"]], saveFileAs)
        else:
            #failed to download, send back an error iq
            errIq = self.xmpp.makeIqError(id=iq['id'], condition='not-acceptable')
            errIq['to'] = iq['from']
            errIq['error']['type'] = 'modify'
            errIq.send()

            
        
        