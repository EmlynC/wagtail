from __future__ import absolute_import, unicode_literals

from django.conf.urls import url
from django.contrib.auth.models import Permission
from django.core.exceptions import ImproperlyConfigured
from django.db.models import Model
from django.forms.widgets import flatatt
from django.utils.safestring import mark_safe
from django.utils.translation import ugettext_lazy as _

from wagtail.wagtailcore import hooks
from wagtail.wagtailcore.models import Page
from wagtail.wagtailimages.models import Filter

from .helpers import (
    AdminURLHelper, ButtonHelper, PageAdminURLHelper, PageButtonHelper, PagePermissionHelper,
    PermissionHelper)
from .menus import GroupMenuItem, ModelAdminMenuItem, SubMenu
from .views import ChooseParentView, CreateView, DeleteView, EditView, IndexView, InspectView


class WagtailRegisterable(object):
    """
    Base class, providing a more convenient way for ModelAdmin or
    ModelAdminGroup instances to be registered with Wagtail's admin area.
    """
    add_to_settings_menu = False
    exclude_from_explorer = False

    def register_with_wagtail(self):

        @hooks.register('register_permissions')
        def register_permissions():
            return self.get_permissions_for_registration()

        @hooks.register('register_admin_urls')
        def register_admin_urls():
            return self.get_admin_urls_for_registration()

        menu_hook = (
            'register_settings_menu_item' if self.add_to_settings_menu else
            'register_admin_menu_item'
        )

        @hooks.register(menu_hook)
        def register_admin_menu_item():
            return self.get_menu_item()

        # Overriding the explorer page queryset is a somewhat 'niche' / experimental
        # operation, so only attach that hook if we specifically opt into it
        # by returning True from will_modify_explorer_page_queryset
        if self.will_modify_explorer_page_queryset():
            @hooks.register('construct_explorer_page_queryset')
            def construct_explorer_page_queryset(parent_page, queryset, request):
                return self.modify_explorer_page_queryset(
                    parent_page, queryset, request)

    def will_modify_explorer_page_queryset(self):
        return False


class ThumbnailMixin(object):
    """
    Mixin class to help display thumbnail images in ModelAdmin listing results.
    `thumb_image_field_name` must be overridden to name a ForeignKey field on
    your model, linking to `wagtailimages.Image`.
    """
    thumb_image_field_name = 'image'
    thumb_image_filter_spec = 'fill-100x100'
    thumb_image_width = 50
    thumb_classname = 'admin-thumb'
    thumb_col_header_text = _('image')
    thumb_default = None

    def admin_thumb(self, obj):
        try:
            image = getattr(obj, self.thumb_image_field_name, None)
        except AttributeError:
            raise ImproperlyConfigured(
                u"The `thumb_image_field_name` attribute on your `%s` class "
                "must name a field on your model." % self.__class__.__name__
            )

        img_attrs = {
            'src': self.thumb_default,
            'width': self.thumb_image_width,
            'class': self.thumb_classname,
        }
        if image:
            fltr = Filter(spec=self.thumb_image_filter_spec)
            img_attrs.update({'src': image.get_rendition(fltr).url})
            return mark_safe('<img{}>'.format(flatatt(img_attrs)))
        elif self.thumb_default:
            return mark_safe('<img{}>'.format(flatatt(img_attrs)))
        return ''
    admin_thumb.short_description = thumb_col_header_text


class ModelAdmin(WagtailRegisterable):
    """
    The core modeladmin class. It provides an alternative means to
    list and manage instances of a given 'model' within Wagtail's admin area.
    It is essentially comprised of attributes and methods that allow a degree
    of control over how the data is represented, and other methods to make the
    additional functionality available via various Wagtail hooks.
    """

    model = None
    menu_label = None
    menu_icon = None
    menu_order = None
    list_display = ('__str__',)
    list_display_add_buttons = None
    inspect_view_fields = []
    inspect_view_fields_exclude = []
    inspect_view_enabled = False
    empty_value_display = '-'
    list_filter = ()
    list_select_related = False
    list_per_page = 100
    search_fields = None
    ordering = None
    parent = None
    index_view_class = IndexView
    create_view_class = CreateView
    edit_view_class = EditView
    inspect_view_class = InspectView
    delete_view_class = DeleteView
    choose_parent_view_class = ChooseParentView
    index_template_name = ''
    create_template_name = ''
    edit_template_name = ''
    inspect_template_name = ''
    delete_template_name = ''
    choose_parent_template_name = ''
    permission_helper_class = None
    url_helper_class = None
    button_helper_class = None
    index_view_extra_css = []
    index_view_extra_js = []
    inspect_view_extra_css = []
    inspect_view_extra_js = []
    form_view_extra_css = []
    form_view_extra_js = []

    def __init__(self, parent=None):
        """
        Don't allow initialisation unless self.model is set to a valid model
        """
        if not self.model or not issubclass(self.model, Model):
            raise ImproperlyConfigured(
                u"The model attribute on your '%s' class must be set, and "
                "must be a valid Django model." % self.__class__.__name__)
        self.opts = self.model._meta
        self.is_pagemodel = issubclass(self.model, Page)
        self.parent = parent
        self.permission_helper = self.get_permission_helper_class()(
            self.model, self.inspect_view_enabled)
        self.url_helper = self.get_url_helper_class()(self.model)


    def get_permission_helper_class(self):
        """
        Returns a permission_helper class to help with permission-based logic
        for the given model.
        """
        if self.permission_helper_class:
            return self.permission_helper_class
        if self.is_pagemodel:
            return PagePermissionHelper
        return PermissionHelper

    def get_url_helper_class(self):
        if self.url_helper_class:
            return self.url_helper_class
        if self.is_pagemodel:
            return PageAdminURLHelper
        return AdminURLHelper

    def get_button_helper_class(self):
        """
        Returns a ButtonHelper class to help generate buttons for the given
        model.
        """
        if self.button_helper_class:
            return self.button_helper_class
        if self.is_pagemodel:
            return PageButtonHelper
        return ButtonHelper

    def get_menu_label(self):
        """
        Returns the label text to be used for the menu item.
        """
        return self.menu_label or self.opts.verbose_name_plural.title()

    def get_menu_icon(self):
        """
        Returns the icon to be used for the menu item. The value is prepended
        with 'icon-' to create the full icon class name. For design
        consistency, the same icon is also applied to the main heading for
        views called by this class.
        """
        if self.menu_icon:
            return self.menu_icon
        if self.is_pagemodel:
            return 'doc-full-inverse'
        return 'snippet'

    def get_menu_order(self):
        """
        Returns the 'order' to be applied to the menu item. 000 being first
        place. Where ModelAdminGroup is used, the menu_order value should be
        applied to that, and any ModelAdmin classes added to 'items'
        attribute will be ordered automatically, based on their order in that
        sequence.
        """
        return self.menu_order or 999

    def get_list_display(self, request):
        """
        Return a sequence containing the fields/method output to be displayed
        in the list view.
        """
        return self.list_display

    def get_list_display_add_buttons(self, request):
        """
        Return the name of the field/method from list_display where action
        buttons should be added. Defaults to the first item from
        get_list_display()
        """
        return self.list_display_add_buttons or self.get_list_display(
            request)[0]

    def get_empty_value_display(self, field_name=None):
        """
        Return the empty_value_display value defined on ModelAdmin
        """
        return mark_safe(self.empty_value_display)

    def get_list_filter(self, request):
        """
        Returns a sequence containing the fields to be displayed as filters in
        the right sidebar in the list view.
        """
        return self.list_filter

    def get_ordering(self, request):
        """
        Returns a sequence defining the default ordering for results in the
        list view.
        """
        return self.ordering or ()

    def get_queryset(self, request):
        """
        Returns a QuerySet of all model instances that can be edited by the
        admin site.
        """
        qs = self.model._default_manager.get_queryset()
        ordering = self.get_ordering(request)
        if ordering:
            qs = qs.order_by(*ordering)
        return qs

    def get_search_fields(self, request):
        """
        Returns a sequence defining which fields on a model should be searched
        when a search is initiated from the list view.
        """
        return self.search_fields or ()

    def get_extra_attrs_for_row(self, obj, context):
        """
        Return a dictionary of HTML attributes to be added to the `<tr>`
        element for the suppled `obj` when rendering the results table in
        `index_view`. `data-object-pk` is already added by default.
        """
        return {}

    def get_extra_class_names_for_field_col(self, obj, field_name):
        """
        Return a list of additional CSS class names to be added to the table
        cell's `class` attribute when rendering the output of `field_name` for
        `obj` in `index_view`.

        Must always return a list.
        """
        return []

    def get_extra_attrs_for_field_col(self, obj, field_name):
        """
        Return a dictionary of additional HTML attributes to be added to a
        table cell when rendering the output of `field_name` for `obj` in
        `index_view`.

        Must always return a dictionary.
        """
        return {}

    def get_index_view_extra_css(self):
        css = ['wagtailmodeladmin/css/index.css']
        css.extend(self.index_view_extra_css)
        return css

    def get_index_view_extra_js(self):
        return self.index_view_extra_js

    def get_form_view_extra_css(self):
        return self.form_view_extra_css

    def get_form_view_extra_js(self):
        return self.form_view_extra_js

    def get_inspect_view_extra_css(self):
        return self.inspect_view_extra_css

    def get_inspect_view_extra_js(self):
        return self.inspect_view_extra_js

    def get_inspect_view_fields(self):
        """
        Return a list of field names, indicating the model fields that
        should be displayed in the 'inspect' view. Returns the value of the
        'inspect_view_fields' attribute if populated, otherwise a sensible
        list of fields is generated automatically, with any field named in
        'inspect_view_fields_exclude' not being included.
        """
        if not self.inspect_view_fields:
            found_fields = []
            for f in self.model._meta.get_fields():
                if f.name not in self.inspect_view_fields_exclude:
                    if f.concrete and (
                        not f.is_relation or
                        (not f.auto_created and f.related_model)
                    ):
                        found_fields.append(f.name)
            return found_fields
        return self.inspect_view_fields

    def index_view(self, request):
        """
        Instantiates a class-based view to provide listing functionality for
        the assigned model. The view class used can be overridden by changing
        the 'index_view_class' attribute.
        """
        kwargs = {'model_admin': self}
        view_class = self.index_view_class
        return view_class.as_view(**kwargs)(request)

    def create_view(self, request):
        """
        Instantiates a class-based view to provide 'creation' functionality for
        the assigned model, or redirect to Wagtail's create view if the
        assigned model extends 'Page'. The view class used can be overridden by
        changing the 'create_view_class' attribute.
        """
        kwargs = {'model_admin': self}
        view_class = self.create_view_class
        return view_class.as_view(**kwargs)(request)

    def choose_parent_view(self, request):
        """
        Instantiates a class-based view to allows a parent page to be chosen
        for a new object, where the assigned model extends Wagtail's Page
        model, and there is more than one potential parent for new instances.
        The view class used can be overridden by changing the
        'choose_parent_view_class' attribute.
        """
        kwargs = {'model_admin': self}
        view_class = self.choose_parent_view_class
        return view_class.as_view(**kwargs)(request)

    def inspect_view(self, request, instance_pk):
        """
        Instantiates a class-based view to provide 'inspect' functionality for
        the assigned model. The view class used can be overridden by changing
        the 'inspect_view_class' attribute.
        """
        kwargs = {'model_admin': self, 'instance_pk': instance_pk}
        view_class = self.inspect_view_class
        return view_class.as_view(**kwargs)(request)

    def edit_view(self, request, instance_pk):
        """
        Instantiates a class-based view to provide 'edit' functionality for the
        assigned model, or redirect to Wagtail's edit view if the assinged
        model extends 'Page'. The view class used can be overridden by changing
        the  'edit_view_class' attribute.
        """
        kwargs = {'model_admin': self, 'instance_pk': instance_pk}
        view_class = self.edit_view_class
        return view_class.as_view(**kwargs)(request)

    def delete_view(self, request, instance_pk):
        """
        Instantiates a class-based view to provide 'delete confirmation'
        functionality for the assigned model, or redirect to Wagtail's delete
        confirmation view if the assinged model extends 'Page'. The view class
        used can be overridden by changing the 'delete_view_class'
        attribute.
        """
        kwargs = {'model_admin': self, 'instance_pk': instance_pk}
        view_class = self.delete_view_class
        return view_class.as_view(**kwargs)(request)

    def get_templates(self, action='index'):
        """
        Utility funtion that provides a list of templates to try for a given
        view, when the template isn't overridden by one of the template
        attributes on the class.
        """
        app_label = self.opts.app_label.lower()
        model_name = self.opts.model_name.lower()
        return [
            'modeladmin/%s/%s/%s.html' % (app_label, model_name, action),
            'modeladmin/%s/%s.html' % (app_label, action),
            'modeladmin/%s.html' % (action,),
        ]

    def get_index_template(self):
        """
        Returns a template to be used when rendering 'index_view'. If a
        template is specified by the 'index_template_name' attribute, that will
        be used. Otherwise, a list of preferred template names are returned.
        """
        return self.index_template_name or self.get_templates('index')

    def get_choose_parent_template(self):
        """
        Returns a template to be used when rendering 'choose_parent_view'. If a
        template is specified by the 'choose_parent_template_name' attribute,
        that will be used. Otherwise, a list of preferred template names are
        returned.
        """
        return self.choose_parent_template_name or self.get_templates(
            'choose_parent')

    def get_inspect_template(self):
        """
        Returns a template to be used when rendering 'inspect_view'. If a
        template is specified by the 'inspect_template_name' attribute, that
        will be used. Otherwise, a list of preferred template names are
        returned.
        """
        return self.inspect_template_name or self.get_templates('inspect')

    def get_create_template(self):
        """
        Returns a template to be used when rendering 'create_view'. If a
        template is specified by the 'create_template_name' attribute,
        that will be used. Otherwise, a list of preferred template names are
        returned.
        """
        return self.create_template_name or self.get_templates('create')

    def get_edit_template(self):
        """
        Returns a template to be used when rendering 'edit_view'. If a template
        is specified by the 'edit_template_name' attribute, that will be used.
        Otherwise, a list of preferred template names are returned.
        """
        return self.edit_template_name or self.get_templates('edit')

    def get_delete_template(self):
        """
        Returns a template to be used when rendering 'delete_view'. If
        a template is specified by the 'delete_template_name'
        attribute, that will be used. Otherwise, a list of preferred template
        names are returned.
        """
        return self.delete_template_name or self.get_templates('delete')

    def get_menu_item(self, order=None):
        """
        Utilised by Wagtail's 'register_menu_item' hook to create a menu item
        to access the listing view, or can be called by ModelAdminGroup
        to create a SubMenu
        """
        return ModelAdminMenuItem(self, order or self.get_menu_order())

    def get_permissions_for_registration(self):
        """
        Utilised by Wagtail's 'register_permissions' hook to allow permissions
        for a model to be assigned to groups in settings. This is only required
        if the model isn't a Page model, and isn't registered as a Snippet
        """
        from wagtail.wagtailsnippets.models import SNIPPET_MODELS
        if not self.is_pagemodel and self.model not in SNIPPET_MODELS:
            return self.permission_helper.get_all_model_permissions()
        return Permission.objects.none()

    def get_admin_urls_for_registration(self):
        """
        Utilised by Wagtail's 'register_admin_urls' hook to register urls for
        our the views that class offers.
        """
        urls = (
            url(self.url_helper.get_action_url_pattern('index'),
                self.index_view,
                name=self.url_helper.get_action_url_name('index')),
            url(self.url_helper.get_action_url_pattern('create'),
                self.create_view,
                name=self.url_helper.get_action_url_name('create')),
            url(self.url_helper.get_action_url_pattern('edit'),
                self.edit_view,
                name=self.url_helper.get_action_url_name('edit')),
            url(self.url_helper.get_action_url_pattern('delete'),
                self.delete_view,
                name=self.url_helper.get_action_url_name('delete')),
        )
        if self.inspect_view_enabled:
            urls = urls + (
                url(self.url_helper.get_action_url_pattern('inspect'),
                    self.inspect_view,
                    name=self.url_helper.get_action_url_name('inspect')),
            )
        if self.is_pagemodel:
            urls = urls + (
                url(self.url_helper.get_action_url_pattern('choose_parent'),
                    self.choose_parent_view,
                    name=self.url_helper.get_action_url_name('choose_parent')),
            )
        return urls

    def will_modify_explorer_page_queryset(self):
        return (self.is_pagemodel and self.exclude_from_explorer)

    def modify_explorer_page_queryset(self, parent_page, queryset, request):
        if self.is_pagemodel and self.exclude_from_explorer:
            queryset = queryset.not_type(self.model)
        return queryset


class ModelAdminGroup(WagtailRegisterable):
    """
    Acts as a container for grouping together mutltiple PageModelAdmin and
    SnippetModelAdmin instances. Creates a menu item with a SubMenu for
    accessing the listing pages of those instances
    """
    items = ()
    menu_label = None
    menu_order = None
    menu_icon = None

    def __init__(self):
        """
        When initialising, instantiate the classes within 'items', and assign
        the instances to a 'modeladmin_instances' attribute for convienient
        access later
        """
        self.modeladmin_instances = []
        for ModelAdminClass in self.items:
            self.modeladmin_instances.append(ModelAdminClass(parent=self))

    def get_menu_label(self):
        return self.menu_label or self.get_app_label_from_subitems()

    def get_app_label_from_subitems(self):
        for instance in self.modeladmin_instances:
            return instance.opts.app_label.title()
        return ''

    def get_menu_icon(self):
        return self.menu_icon or 'icon-folder-open-inverse'

    def get_menu_order(self):
        return self.menu_order or 999

    def get_menu_item(self):
        """
        Utilised by Wagtail's 'register_menu_item' hook to create a menu
        for this group with a SubMenu linking to listing pages for any
        associated ModelAdmin instances
        """
        if self.modeladmin_instances:
            submenu = SubMenu(self.get_submenu_items())
            return GroupMenuItem(self, self.get_menu_order(), submenu)

    def get_submenu_items(self):
        menu_items = []
        item_order = 1
        for modeladmin in self.modeladmin_instances:
            menu_items.append(modeladmin.get_menu_item(order=item_order))
            item_order += 1
        return menu_items

    def get_permissions_for_registration(self):
        """
        Utilised by Wagtail's 'register_permissions' hook to allow permissions
        for a all models grouped by this class to be assigned to Groups in
        settings.
        """
        qs = Permission.objects.none()
        for instance in self.modeladmin_instances:
            qs = qs | instance.get_permissions_for_registration()
        return qs

    def get_admin_urls_for_registration(self):
        """
        Utilised by Wagtail's 'register_admin_urls' hook to register urls for
        used by any associated ModelAdmin instances
        """
        urls = tuple()
        for instance in self.modeladmin_instances:
            urls += instance.get_admin_urls_for_registration()
        return urls

    def will_modify_explorer_page_queryset(self):
        return any(
            instance.will_modify_explorer_page_queryset()
            for instance in self.modeladmin_instances
        )

    def modify_explorer_page_queryset(self, parent_page, queryset, request):
        for instance in self.modeladmin_instances:
            queryset = instance.modify_explorer_page_queryset(
                parent_page, queryset, request)
        return queryset


def modeladmin_register(modeladmin_class):
    """
    Method for registering ModelAdmin or ModelAdminGroup classes with Wagtail.
    """
    instance = modeladmin_class()
    instance.register_with_wagtail()
