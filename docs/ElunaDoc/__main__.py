import os
import shutil
from types import FileType
from jinja2 import Environment, FileSystemLoader
from typedecorator import params, returns
from parser import ClassParser, MethodDoc
import glob
import time
import re
import sys

@returns([(str, FileType)])
@params(search_path=str)
def find_class_files(search_path):
    """Find and open all files containing Eluna class methods in `search_path`.

    :param search_path: the path to search for Eluna methods in
    :return: a list of all files containing Eluna methods, and the name of their respective classes
    """
    # Get the current working dir and switch to the search path.
    old_dir = os.getcwd()
    os.chdir(search_path)
    # Search for all files ending in "Methods.h".
    method_file_names = glob.glob('*Methods.h')
    # Open each file.
    method_files = [open(file_name, 'r') for file_name in method_file_names]
    # Go back to where we were before.
    os.chdir(old_dir)
    return method_files


def make_renderer(template_path, link_parser_factory):
    """Return a function that can be used to render Jinja2 templates from the `template_path` directory."""

    # Set up jinja2 environment to load templates from the templates folder.
    env = Environment(loader=FileSystemLoader(template_path), extensions=['jinja2.ext.with_'])


    def inner(template_name, output_path, level, **kwargs):
        env.filters['parse_links'], env.filters['parse_data_type'] = link_parser_factory(level)
        template = env.get_template(template_name)
        static = make_static(level)
        root = make_root(level)
        currdate = time.strftime("%d/%m/%Y")

        with open('build/' + output_path, 'w') as out:
            out.write(template.render(level=level, static=static, root=root, currdate=currdate, **kwargs))

    return inner


def make_static(level):
    return lambda file_name: ('../' * level) + 'static/' + file_name


def make_root(level):
    return lambda file_name: ('../' * level) + file_name


if __name__ == '__main__':
    # Recreate the build folder and copy static files over.
    if os.path.exists('build'):
        shutil.rmtree('build')
    os.mkdir('build')
    shutil.copytree('ElunaDoc/static', 'build/static')

    # Load up all files with methods we need to parse.
    print 'Finding Eluna method files...'
    class_files = find_class_files('../')

    # Parse all the method files.
    classes = []
    for f in class_files:
        print 'Parsing file {}...'.format(f.name)
        classes.append(ClassParser.parse_file(f))
        f.close()

    # Sort the classes so they are in the correct order in lists.
    classes.sort(key=lambda c: c.name)

    def make_parsers(level):
        """Returns a function that parses content for refs to other classes, methods, or enums,
        and automatically inserts the correct link.
        """
        # Make lists of all class names and method names.
        class_names = []
        method_names = []

        for class_ in classes:
            class_names.append('[' + class_.name + ']')

            for method in class_.methods:
                method_names.append('[' + class_.name + ':' + method.name + ']')

        def link_parser(content):
            # Replace all occurrencies of &Class:Function and then &Class with a link to given func or class

            for name in method_names:
                # Take the [] off the front of the method's name.
                full_name = name[1:-1]
                # Split "Class:Method" into "Class" and "Method".
                class_name, method_name = full_name.split(':')
                url = '{}{}/{}.html'.format(('../' * level), class_name, method_name)
                # Replace occurrencies of &Class:Method with the url created
                content = content.replace(name, '<a class="fn" href="{}">{}</a>'.format(url, full_name))

            for name in class_names:
                # Take the [] off the front of the class's name.
                class_name = name[1:-1]
                url = '{}{}/index.html'.format(('../' * level), class_name)
                # Replace occurrencies of &Class:Method with the url created
                content = content.replace(name, '<a class="mod" href="{}">{}</a>'.format(url, class_name))

            return content

        # Links to the "Programming in Lua" documentation for each Lua type.
        lua_type_documentation = {
            'nil': 'http://www.lua.org/pil/2.1.html',
            'boolean': 'http://www.lua.org/pil/2.2.html',
            'number': 'http://www.lua.org/pil/2.3.html',
            'string': 'http://www.lua.org/pil/2.4.html',
            'table': 'http://www.lua.org/pil/2.5.html',
            'function': 'http://www.lua.org/pil/2.6.html',
            '...': 'http://www.lua.org/pil/5.2.html',
        }

        def data_type_parser(content):
            # If the type is a Lua type, return a link to Lua documentation.
            if content in lua_type_documentation:
                url = lua_type_documentation[content]
                return '<strong><a href="{}">{}</a></strong>'.format(url, content)

            # Otherwise try to build a link to the proper page.
            if content in class_names:
                class_name = content[1:-1]
                url = '{}{}/index.html'.format(('../' * level), class_name)
                return '<strong><a class="mod" href="{}">{}</a></strong>'.format(url, class_name)

            # Case for enums to direct to a search on github
            enum_name = content[1:-1]
            url = 'https://github.com/ElunaLuaEngine/ElunaTrinityWotlk/search?l=cpp&q=%22enum+{}%22&type=Code&utf8=%E2%9C%93'.format(enum_name)
            return '<strong><a href="{}">{}</a></strong>'.format(url, enum_name)

            # By default we just return the name without the [] around it
            return content[1:-1]

        return link_parser, data_type_parser

    # Create the render function with the template path and parser maker.
    render = make_renderer('ElunaDoc/templates', make_parsers)

    # Render the index.
    render('index.html', 'index.html', level=0, classes=classes)
    # Render the search index.
    render('search-index.js', 'search-index.js', level=0, classes=classes)

    for class_ in classes:
        print 'Rending pages for class {}...'.format(class_.name)

        # Make a folder for the class.
        os.mkdir('build/' + class_.name)
        index_path = '{}/index.html'.format(class_.name)

        # Render the class's index page.
        render('class.html', index_path, level=1, classes=classes, current_class=class_)

        # Render each method's page.
        for method in class_.methods:
            method_path = '{}/{}.html'.format(class_.name, method.name)
            render('method.html', method_path, level=1, current_class=class_, current_method=method)

    # ts-wow generation
    enums = []
    globaldts = ""
    def app(str,*args):
        global globaldts
        globaldts+=(str.format(*args))


    def translate_type(t):
        t = t.translate(None,"[]")
        if t == "Map":
            return "EMap"
        if t == "table":
            return "any"
        if t == "Object":
            return "EObject"
        return t

    types = [
        "number","boolean","string"
    ]

    for class_ in classes:
        types.append(translate_type(class_.name))

    def fix_type(n,t):
        t = translate_type(t)
        if not t in types:
            t = "number"
        if n == "...": t = t+"[]"
        return t

    def fix_name(name):
        if name == "function": return "func"
        if name == "...": return "...args"
        return name

    if "--enums" in sys.argv:
        for class_ in classes:
            for method in class_.methods:
                desc = method.raw_description
                desc = desc.split("\n")
                in_enum = False
                enum_text = ""
                enum_name = ""
                for i,v in enumerate(desc):
                    # hackfix
                    if v == "    EFFECT_MOTION_TYPE              = 16, // TC":
                        v = "    EFFECT_MOTION_TYPE_TC           = 16, // TC"

                    # style fixes
                    if "        {" in v:
                        v = v.replace("        {","    {")

                    if "    enum" in v:
                        v = v.replace("    enum","enum")

                    enum_match = re.match("enum ([a-zA-Z]+)",v)
                    if enum_match:
                        in_enum = True
                        enum_name = enum_match.group(1)

                    if "enum " in v: in_enum = True
                    if in_enum:
                        enum_text+=v.translate(None,";")+"\n"
                        if "}" in v:
                            in_enum = False
                            if not enum_name in enums:
                                app("declare {}",enum_text)
                                enums.append(enum_name)
                                types.append(enum_name)
                                enum_text = ""

    # pass 2: classes
    for class_ in classes:
        app("declare class {} {{\n",fix_type(None,class_.name))
        for method in class_.methods:
            desc = method.raw_description
            desc = desc.split("\n")
            desc = filter(lambda x:len(x)>0,desc)
            desc = map(lambda x: "     * {}".format(x),desc)
            desc = "\n".join(desc)
            app("    /**\n{}\n     */\n",desc)
            app("    {}(",method.name)
            for i,param in enumerate(method.parameters):
                app("{}: {}",fix_name(param.name),fix_type(param.name,param.data_type))
                if(i<len(method.parameters)-1):
                    app(", ")
            app(")")

            if len(method.returned) > 0:
                app(": ")

            is_multi = len(method.returned) > 1
            if is_multi: app("[")
            for i,param in enumerate(method.returned):
                app(fix_type(param.name,param.data_type))

                if is_multi and i<len(method.returned)-1:
                    app(", ")

            if is_multi: app("]")

            app("\n\n")
        app("}}\n\n")

    f = open("build/global.d.ts","w")
    f.write(globaldts)
    f.close()