"""Implementations of Python fundamental objects for Byterun."""

import collections, inspect, types

def make_cell(value):
    # Thanks to Alex Gaynor for help with this bit of twistiness.
    # Construct an actual cell object by creating a closure right here,
    # and grabbing the cell object out of the function we create.
    fn = (lambda x: lambda: x)(value)
    return fn.__closure__[0]

class Function(object):
    __slots__ = [
        'func_code', 'func_name', 'func_defaults', 'func_globals',
        'func_locals', 'func_dict', 'func_closure',
        '__name__', '__dict__', '__doc__',
        '_vm', '_func',
    ]

    def __init__(self, name, code, globs, defaults, closure, vm):
        self._vm = vm
        self.func_code = code
        self.func_name = self.__name__ = name or code.co_name
        self.func_defaults = tuple(defaults)
        self.func_globals = globs
        self.func_locals = self._vm.frame.f_locals
        self.__dict__ = {}
        self.func_closure = closure
        self.__doc__ = code.co_consts[0] if code.co_consts else None

        # Sometimes, we need a real Python function.  This is for that.
        kw = {
            'argdefs': self.func_defaults,
        }
        if closure:
            kw['closure'] = tuple(make_cell(0) for _ in closure)
        self._func = types.FunctionType(code, globs, **kw)

    def __repr__(self):         # pragma: no cover
        return '<Function %s at 0x%08x>' % (
            self.func_name, id(self)
        )

    def __get__(self, instance, owner):
        if instance is not None:
            return Method(instance, owner, self)
        return self

    def __call__(self, *args, **kwargs):
        callargs = inspect.getcallargs(self._func, *args, **kwargs)
        frame = self._vm.make_frame(
            self.func_code, callargs, self.func_globals, self.func_locals
        )
        return self._vm.run_frame(frame)


class Class(object):
    def __init__(self, name, bases, methods):
        self.__name__ = name
        self.__bases__ = bases
        self.locals = methods

    def __call__(self, *args, **kw):
        return Object(self, self.locals, args, kw)

    def __repr__(self):         # pragma: no cover
        return '<Class %s at 0x%08x>' % (self.__name__, id(self))

    def __getattr__(self, name):
        try:
            val = self.locals[name]
        except KeyError:
            raise AttributeError("Fooey: %r" % (name,))
        # Check if we have a descriptor
        get = getattr(val, '__get__', None)
        if get:
            return get(None, self)
        # Not a descriptor, return the value.
        return val


class Object(object):
    def __init__(self, _class, methods, args, kw):
        self._class = _class
        self.locals = methods
        if '__init__' in methods:
            methods['__init__'](self, *args, **kw)

    def __repr__(self):         # pragma: no cover
        return '<%s Instance at 0x%08x>' % (self._class.__name__, id(self))

    def __getattr__(self, name):
        try:
            val = self.locals[name]
        except KeyError:
            raise AttributeError(
                "%r object has no attribute %r" % (self._class.__name__, name)
            )
        # Check if we have a descriptor
        get = getattr(val, '__get__', None)
        if get:
            return get(self, self._class)
        # Not a descriptor, return the value.
        return val


class Method(object):
    def __init__(self, obj, _class, func):
        self.im_self = obj
        self.im_class = _class
        self.im_func = func

    def __repr__(self):         # pragma: no cover
        name = "%s.%s" % (self.im_class.__name__, self.im_func.func_name)
        if self.im_self is not None:
            return '<Bound Method %s of %s>' % (name, self.im_self)
        else:
            return '<Unbound Method %s>' % (name,)

    def __call__(self, *args, **kwargs):
        if self.im_self is not None:
            return self.im_func(self.im_self, *args, **kwargs)
        else:
            return self.im_func(*args, **kwargs)

Block = collections.namedtuple("Block", "type, handler, level")


class Frame(object):
    def __init__(self, f_code, f_globals, f_locals, f_back):
        self.f_code = f_code
        self.f_globals = f_globals
        self.f_locals = f_locals
        self.f_back = f_back
        if f_back:
            self.f_builtins = f_back.f_builtins
        else:
            self.f_builtins = f_locals['__builtins__']
            if hasattr(self.f_builtins, '__dict__'):
                self.f_builtins = self.f_builtins.__dict__

        self.f_lineno = f_code.co_firstlineno
        self.f_lasti = 0

        if f_code.co_cellvars:
            self.cells = {}
            if not f_back.cells:
                f_back.cells = {}
            for var in f_code.co_cellvars:
                f_back.cells[var] = self.cells[var]
        else:
            self.cells = None

        if f_code.co_freevars:
            if not self.cells:
                self.cells = {}
            for var in f_code.co_freevars:
                assert self.cells is not None
                assert f_back.cells, "f_back.cells: %r" % (f_back.cells,)
                self.cells[var] = f_back.cells[var]

        self.block_stack = []

    def __repr__(self):         # pragma: no cover
        return '<Frame at 0x%08x>' % id(self)

