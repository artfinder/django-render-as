import os.path
import traceback

from django import template
from django.conf import settings
from django.template import Context
from django.template.loader import render_to_string
from django.core.urlresolvers import reverse, resolve

register = template.Library()

@register.tag
def render_as(parser, token):
    """
    Template tag which renders a suitable template for the object. Call as:
    
    {% render_as obj type %}
    
    The template is found by looking in order for:
    
     * <app>/<model>_<type>.html
     * render_as/default_<type>.html
     
    and rendering with the context at the time of the call, updated to
    include `object` as the first parameter to the {% render_as ... %} call.
    """

    try:
        tag_name, object_ref, type = token.split_contents()
    except ValueError:
        raise template.TemplateSyntaxError, u"'%s' tag requires two arguments" % token.contents.split()[0]
    return RenderAsNode(object_ref, type)


class RenderAsNode(template.Node):
    def __init__(self, object_ref, type):
        self.object = template.Variable(object_ref)
        self.type = type
        
    def render(self, context):
        result = u""
        try:
            object = self.object.resolve(context)
        except template.VariableDoesNotExist:
            if settings.TEMPLATE_DEBUG:
                traceback.print_exc()
                return u"[[ no such variable '%s' in render_as call ]]" % self.object
            else:
                return u""

        try:
            widget_type = template.Variable(self.type).resolve(context)
        except template.VariableDoesNotExist:
            widget_type = self.type.strip("'\"")

        try:
            # default to <app>/<model>...
            app_name = object.__class__._meta.app_label
            model_name = object.__class__._meta.module_name
        except AttributeError:
            # fall back to most specific module and lowercased
            # class name
            app_name = type(object).__module__.split(".")[-1]
            model_name = object.__class__.__name__.lower()

        def default_widget_context_data(widget_type, context):
            return context

        get_widget_context = getattr(object, "get_widget_context_data", default_widget_context_data)

        # build a whole new context for the widget invocation
        widget_context = get_widget_context(widget_type, context)
        # if we get a Context object then use it as-is. otherwise push a new element onto the calling stack
        if not isinstance(widget_context, Context):
            context.update(widget_context)
            widget_context = context
        else:
            # push an empty element onto the stack so that we can always pop() the same number of times
            widget_context.push()

        widget_context.update({'object': object})

        try:
            widget_context.push()
            main_template = os.path.join(app_name, "render_as", "%s_%s.html" % (model_name, widget_type))
            backup_template = os.path.join('render_as', "default_%s.html" % (widget_type,))
            result = render_to_string([main_template, backup_template], context_instance=widget_context)
        
        except template.TemplateDoesNotExist, e:
            if settings.TEMPLATE_DEBUG:
                traceback.print_exc()
                result = u"[[ no such template in render_as call (%s) ]]" % ", ".join([main_template, backup_template])
        
        except template.TemplateSyntaxError, e:
            if settings.TEMPLATE_DEBUG:
                traceback.print_exc()
                result = u"[[ template syntax error in render_as call (%s) ]]" % ", ".join([main_template, backup_template])
        finally:
            widget_context.pop()
            widget_context.pop()
        
        return result
