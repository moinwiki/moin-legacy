# -*- coding: iso-8859-1 -*-
"""
    MoinMoin - XML Serialization

    Copyright (c) 2002 by J�rgen Hermann <jh@web.de>
    All rights reserved, see COPYING for details.

    $Id: marshal.py,v 1.3 2003/11/09 21:01:18 thomaswaldmann Exp $
"""

import types


class Marshal:
    """ Serialize Python data structures to XML.

        XML_DECL is the standard XML declaration.

        The class attributes ROOT_CONTAINER (default "data") and
        ITEM_CONTAINER (default "item") can be overwritten by derived
        classes; if ROOT_CONTAINER is `None`, the usually generated
        container element is omitted, the same is true for ITEM_CONTAINER.
        
        PRIVATE_PREFIXES is a list of prefixes of tagnames that are
        treated as private, i.e. things that should not be serialized.
        Default is to omit all properties starting with an underscore.

        TAG_MAP is a translation table for tag names, and is empty by
        default. It can also be used to surpress certain properties by
        mapping a tag name to `None`.
    """

    # Convenience: Standard-XML-Deklaration
    XML_DECL = '<?xml version="1.0" encoding="ISO-8859-1"?>\n'

    # Container Tags
    ROOT_CONTAINER = "data"
    ITEM_CONTAINER = "item"
    
    # List of private prefixes
    PRIVATE_PREFIXES = ['_']

    # Translation map
    TAG_MAP = {}


    def __toXML(self, element, data): 
        """ Recursive helper method that transforms an object to XML.
        
            Returns a list of strings, which constitute the XML document.
        """
        # map tag names
        if self.TAG_MAP:
            element = self.TAG_MAP.get(element, element)

        if element:
            for prefix in self.PRIVATE_PREFIXES:
                if element.startswith(prefix): return ''
            content = ['<%s>' % element]
        else:
            content = []

        # Handle the different data types
        add_content = content.extend

        if data is None:
            content = "<none/>"

        elif isinstance(data, types.StringType):
            # String
            content = (data.replace("&", "&amp;") # Must be done first!
                           .replace("<", "&lt;")
                           .replace(">", "&gt;"))

        elif isinstance(data, types.DictionaryType):
            # Dictionary
            for key, value in data.items():
                add_content(self.__toXML(key, value))

        elif isinstance(data, types.ListType) or isinstance(data, types.TupleType):
            # List or Tuple
            for item in data:
                add_content(self.__toXML(self.ITEM_CONTAINER, item))

        elif hasattr(data, "toXML"):
            add_content([data.toXML()])

        elif hasattr(data, "__dict__"):
            add_content(self.__toXML(self.ROOT_CONTAINER, data.__dict__))

        else:
            # Everything else
            content = (str(data).replace("&", "&amp;") # Must be done first!
                                .replace("<", "&lt;")
                                .replace(">", "&gt;"))

        # Close container element
        if isinstance(content, types.StringType):
            # No Whitespace
            if element:
                content = ['<%s>%s</%s>' % (element, content, element)]
            else:
                content = [content]
        elif element:
            # Whitespace
            content.append('</%s>' % element)

        return content


    def toXML(self):
        """ Transform an instance to an XML string.
        """
        return '\n'.join(self.__toXML(self.ROOT_CONTAINER, self.__dict__))
