#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""InStock quant package."""

import os

# Extend package search path so that sibling directories (core, job, web)
# in dev environment are seamlessly resolved under the `instock.` namespace.
_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent not in __path__:
    __path__.append(_parent)

__author__ = 'myh'
