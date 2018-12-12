# -*- coding: utf-8 -*-

class PLCDataObject:

    def __init__(self, **kwargs):
        name = self.__class__.__name__
        for key, value in kwargs.items():
            if not hasattr(self, key):
                raise Exception('%s does not have attribute %s' % (name, key))
            originalType = type(getattr(self, key))
            valueType = type(value)
            if originalType != valueType:
                raise Exception('attribute %s of %s is of type %r, but passed in value is of type %r' % (key, name, originalType, valueType))
            setattr(self, key, value)

    def __repr__(self):
        name = self.__class__.__name__
        kwargs = [
            '%s=%r' % (key, getattr(self, key))
            for key in dir(self.__class__)
            if not key.startswith('_') and getattr(self, key) != getattr(self.__class__, key)
        ]
        return '<%s(%s)>' % (name, ', '.join(kwargs))
