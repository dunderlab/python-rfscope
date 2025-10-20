# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Path setup --------------------------------------------------------------

# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.
#
import os
import sys

sys.path.insert(0, os.path.abspath('../../'))

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = 'RF-Scope'
copyright = '2025, Yeison Cardona'
author = 'Yeison Cardona'

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    'nbsphinx',
    'dunderlab.docs',
]

templates_path = ['_templates']
exclude_patterns = []



# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'alabaster'
html_static_path = ['_static']

html_logo = '_static/logo.svg'
html_favicon = '_static/favicon.ico'

html_theme_options = {
    'caption_font_family': 'Noto Sans',
    'font_family': 'Noto Sans',
    'head_font_family': 'Noto Sans',
    'page_width': '1280px',
    'sidebar_width': '300px',
}

dunderlab_color_links = '#FFA500'
dunderlab_code_reference = True
dunderlab_github_repository = "https://github.com/dunderlab/python-rfscope"

# -- Include documentation from docstrings -----------------------------------
# https://www.sphinx-doc.org/en/master/usage/extensions/autodoc.html#module-sphinx.ext.autodoc

# The default options for autodoc directives. They are applied to all autodoc directives automatically.
# Setting None or True to the value is equivalent to giving only the option name to the directives.
autodoc_default_options = {
    'members': None,  # Include members of the module (classes, functions, etc.)
    'undoc-members': None,  # Include members that are not documented
    'private-members': False,  # Include private members (those starting with an underscore _)
    'special-members': False,  # Include special members (e.g., __init__, __repr__)
    # 'imported-members': None,  # Include members imported from other modules
    'inherited-members': None,  # Include inherited members
    'show-inheritance': None,  # Show the inheritance diagram
    'ignore-module-all': False,  # Ignore the __all__ attribute of the module
    # 'exclude-members': '__weakref__',  # Exclude specific members
}

# Uncomment one of the following lines to set the desired behavior for class content
autoclass_content = 'class'  # Only the class’ docstring is inserted (default)
# autoclass_content = 'both'  # Both the class’ and the __init__ method’s docstring are concatenated and inserted
# autoclass_content = 'init'  # Only the __init__ method’s docstring is inserted

# Uncomment one of the following lines to set the desired display for class signatures
autodoc_class_signature = 'mixed'  # Display the signature with the class name (default)
# autodoc_class_signature = 'separated'  # Display the signature as a method

# Uncomment one of the following lines to set the desired order for documented members
autodoc_member_order = 'alphabetical'  # Members are sorted alphabetically (default)
# autodoc_member_order = 'groupwise'  # Members are sorted by member type
# autodoc_member_order = 'bysource'  # Members are sorted by the order in the source code

# Uncomment one of the following lines to set the desired behavior for typehints
autodoc_typehints = 'signature'  # Show typehints in the signature (default)
# autodoc_typehints = 'description'  # Show typehints as content of the function or method
# autodoc_typehints = 'none'  # Do not show typehints
# autodoc_typehints = 'both'  # Show typehints in the signature and as content of the function or method

# Uncomment one of the following lines to set the desired behavior for documenting types of undocumented parameters and return values
autodoc_typehints_description_target = (
    'all'  # Types are documented for all parameters and return values (default)
)
# autodoc_typehints_description_target = 'documented'  # Types are documented only for parameters or return values that are already documented by the docstring
# autodoc_typehints_description_target = 'documented_params'  # Parameter types are annotated if documented in the docstring; return type is always annotated (except if None)

# Uncomment one of the following lines to set the desired format for typehints
autodoc_typehints_format = (
    'short'  # Suppress the leading module names of the typehints (default)
)
# autodoc_typehints_format = 'fully-qualified'  # Show the module name and its name of typehints


# autodoc_mock_imports
# This value contains a list of modules to be mocked up. This is useful when some external dependencies
# are not met at build time and break the building process. You may only specify the root package of
# the dependencies themselves and omit the sub-modules.
autodoc_mock_imports = [
    # Uncomment the modules you need to mock
    "numpy",
    "matplotlib",
]


def setup(app):
    app.add_css_file('custom_rfscope.css')
