# -*- coding: iso-8859-1 -*-
"""
	MoinMoin - Java Source Parser

	Copyright (c) 2002 by Taesu Pyo <bigflood@hitel.net>
	All rights reserved.

"""

from MoinMoin.util.ParserBase import ParserBase

class Parser(ParserBase):

    parsername = "ColorizedJava"
    extensions = ['.java']

    def setupRules(self):
        ParserBase.setupRules(self)

        self.addRulePair("Comment","/[*]","[*]/")
        self.addRule("Comment","//.*$")
        self.addRulePair("String",'"',r'$|[^\\](\\\\)*"')
        self.addRule("Char",r"'\\.'|'[^\\]'")
        self.addRule("Number",r"[0-9](\.[0-9]*)?(eE[+-][0-9])?[flFLdD]?|0[xX][0-9a-fA-F]+[Ll]?")
        self.addRule("ID","[a-zA-Z_][0-9a-zA-Z_]*")
        self.addRule("SPChar",r"[~!%^&*()+=|\[\]:;,.<>/?{}-]")

        reserved_words = ['class','interface','enum','import','package',
        'byte','int','long','float','double','char','short','void','boolean',
        'static','final','const','private','public','protected',
        'new','this','super','abstract','native','synchronized','transient','volatile','strictfp',
        'extends','implements','if','else','while','for','do','switch','case','default','instanceof',
        'try','catch','finally','throw','throws','return','continue','break']

        self.addReserved(reserved_words)

        constant_words = ['true','false','null']

        self.addConstant(constant_words)
