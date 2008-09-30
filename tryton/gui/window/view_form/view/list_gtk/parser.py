#This file is part of Tryton.  The COPYRIGHT file at the top level of this repository contains the full copyright notices and license terms.
import locale
import gtk
import math

from tryton.rpc import RPCProxy
from editabletree import EditableTreeView
from tryton.gui.window.view_form.view.interface import ParserInterface

import time

from tryton.gui.window.view_form.view.form_gtk.many2one import Dialog \
        as M2ODialog
from tryton.gui.window.view_form.view.form_gtk.one2many import Dialog \
        as O2MDialog
from tryton.gui.window.win_search import WinSearch

import tryton.rpc as rpc
import datetime as DT
from tryton.common import DT_FORMAT, DHM_FORMAT, COLORS, node_attributes, \
        TRYTON_ICON, HM_FORMAT
import tryton.common as common
from tryton.common.cellrendererbutton import CellRendererButton
from tryton.common.cellrendererdate import CellRendererDate
from tryton.common.cellrenderertext import CellRendererText
from tryton.action import Action
from tryton.translate import date_format
import mx.DateTime

def send_keys(renderer, editable, position, treeview):
    editable.connect('key_press_event', treeview.on_keypressed)
    editable.editing_done_id = editable.connect('editing_done',
            treeview.on_editing_done)
    if isinstance(editable, gtk.ComboBoxEntry):
        editable.connect('changed', treeview.on_editing_done)

def sort_model(column, treeview, screen):
    for col in treeview.get_columns():
        if col != column:
            col.arrow_show = False
            col.arrow.hide()
    screen.sort = None
    if not column.arrow_show:
        column.arrow_show = True
        column.arrow.set(gtk.ARROW_DOWN, gtk.SHADOW_IN)
        column.arrow.show()
        screen.sort = [(column.name, 'ASC')]
    else:
        if column.arrow.get_property('arrow-type') == gtk.ARROW_DOWN:
            column.arrow.set(gtk.ARROW_UP, gtk.SHADOW_IN)
            screen.sort = [(column.name, 'DESC')]
        else:
            column.arrow_show = False
            column.arrow.hide()
    model = treeview.get_model()
    if screen.search_count == len(model):
        ids = screen.search_filter(only_ids=True)
        model.sort(ids)
    else:
        screen.search_filter()

class ParserTree(ParserInterface):

    def __init__(self, window, parent=None, attrs=None, screen=None):
        super(ParserTree, self).__init__(window, parent, attrs, screen)
        self.treeview = None

    def parse(self, model, root_node, fields):
        dict_widget = {}
        button_list = []
        attrs = node_attributes(root_node)
        on_write = attrs.get('on_write', '')
        editable = attrs.get('editable', False)
        if editable:
            treeview = EditableTreeView(editable)
        else:
            treeview = gtk.TreeView()
            treeview.cells = {}
        treeview.sequence = attrs.get('sequence', False)
        treeview.colors = {}
        self.treeview = treeview
        for color_spec in attrs.get('colors', '').split(';'):
            if color_spec:
                colour, test = color_spec.split(':')
                self.treeview.colors[colour] = test
        treeview.set_property('rules-hint', True)
        if not self.title:
            self.title = attrs.get('string', 'Unknown')
        tooltips = gtk.Tooltips()

        for node in root_node.childNodes:
            node_attrs = node_attributes(node)
            if node.localName == 'field':
                fname = str(node_attrs['name'])
                for boolean_fields in ('readonly', 'required'):
                    if boolean_fields in node_attrs:
                        node_attrs[boolean_fields] = \
                                bool(int(node_attrs[boolean_fields]))
                if fname not in fields:
                    continue
                fields[fname].update(node_attrs)
                node_attrs.update(fields[fname])
                cell = CELLTYPES.get(node_attrs.get('widget',
                    fields[fname]['type']))(fname, model,
                    treeview, node_attrs, self.window)
                treeview.cells[fname] = cell
                renderer = cell.renderer

                readonly = not (editable and not node_attrs.get('readonly', False))
                if isinstance(renderer, gtk.CellRendererToggle):
                    renderer.set_property('activatable', not readonly)
                elif isinstance(renderer,
                        (gtk.CellRendererProgress, CellRendererButton)):
                    pass
                else:
                    renderer.set_property('editable', not readonly)
                if not readonly:
                    renderer.connect_after('editing-started', send_keys,
                            treeview)

                col = gtk.TreeViewColumn(fields[fname]['string'], renderer)
                col.name = fname

                hbox = gtk.HBox(False, 2)
                label = gtk.Label(fields[fname]['string'])
                label.show()
                help = fields[fname]['string']
                if fields[fname].get('help'):
                    help += '\n' + fields[fname]['help']
                tooltips.set_tip(label, help)
                tooltips.enable()
                arrow = gtk.Arrow(gtk.ARROW_DOWN, gtk.SHADOW_IN)
                col.arrow = arrow
                col.arrow_show = False
                hbox.pack_start(label, True, True, 0)
                hbox.pack_start(arrow, False, False, 0)
                hbox.show()
                col.set_widget(hbox)

                col._type = fields[fname]['type']
                col.set_cell_data_func(renderer, cell.setter)
                col.set_clickable(True)
                twidth = {
                    'integer': 60,
                    'float': 80,
                    'numeric': 80,
                    'float_time': 80,
                    'date': 90,
                    'datetime': 140,
                    'selection': 90,
                    'char': 100,
                    'one2many': 50,
                    'many2many': 50,
                    'boolean': 20,
                }
                if 'width' in fields[fname]:
                    width = int(fields[fname]['width'])
                else:
                    width = twidth.get(fields[fname]['type'], 100)
                col.width = width
                if width > 0:
                    col.set_fixed_width(width)
                #XXX doesn't work well when resize columns
                #col.set_expand(True)
                if not treeview.sequence and node_attrs.get('sortable', True):
                    col.connect('clicked', sort_model, treeview, self.screen)
                col.set_resizable(True)
                col.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
                col.set_visible(not fields[fname].get('tree_invisible', False))
                i = treeview.append_column(col)
                if 'sum' in fields[fname] and fields[fname]['type'] \
                        in ('integer', 'float', 'numeric', 'float_time'):
                    label = gtk.Label()
                    label.set_use_markup(True)
                    label_str = fields[fname]['sum'] + ': '
                    label_bold = bool(int(fields[fname].get('sum_bold', 0)))
                    if label_bold:
                        label.set_markup('<b>%s</b>' % label_str)
                    else:
                        label.set_markup(label_str)
                    label_sum = gtk.Label()
                    label_sum.set_use_markup(True)
                    if isinstance(fields.get('digits'), str):
                        digits = 2
                    else:
                        digits = fields.get('digits', (16, 2))[1]
                    dict_widget[i] = (fname, label, label_sum, digits,
                            label_bold)
            elif node.localName == 'button':
                #TODO add shortcut
                cell = Button(treeview, node_attrs, self.window, self.screen)
                button_list.append(cell)
                renderer = cell.renderer
                string = node_attrs.get('string', _('Unknown'))
                col = gtk.TreeViewColumn(string, renderer)
                col.name = None

                label = gtk.Label(string)
                label.show()
                help = string
                if node_attrs.get('help'):
                    help += '\n' + node_attrs['help']
                tooltips.set_tip(label, help)
                tooltips.enable()
                arrow = gtk.Arrow(gtk.ARROW_DOWN, gtk.SHADOW_IN)
                col.arrow = arrow
                col.arrow_show = False
                col.set_widget(label)

                col._type = 'button'
                if 'width' in node_attrs:
                    width = int(node_attrs['width'])
                else:
                    width = 80
                col.width = width
                if width > 0:
                    col.set_fixed_width(width)
                col.set_resizable(True)
                col.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
                i = treeview.append_column(col)
        if not bool(int(attrs.get('fill', '0'))):
            col = gtk.TreeViewColumn()
            col.name = None
            arrow = gtk.Arrow(gtk.ARROW_DOWN, gtk.SHADOW_IN)
            col.arrow = arrow
            col.arrow_show = False
            col._type = 'fill'
            col.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
            treeview.append_column(col)
        treeview.set_fixed_height_mode(True)
        return treeview, dict_widget, button_list, on_write, [], None


class Char(object):

    def __init__(self, field_name, model, treeview=None, attrs=None,
            window=None):
        self.field_name = field_name
        self.model = model
        self.attrs = attrs or {}
        self.renderer = CellRendererText()
        self.treeview = treeview
        self.window = window

    def setter(self, column, cell, store, iter):
        model = store.get_value(iter, 0)
        text = self.get_textual_value(model)
        cell.set_property('text', text)
        color = self.get_color(model)
        cell.set_property('foreground', str(color))
        if self.attrs['type'] in ('float', 'integer', 'boolean', 'numeric',
                'float_time'):
            align = 1
        else:
            align = 0
        if hasattr(self.treeview, 'editable') \
                and self.treeview.editable:
            field = model[self.field_name]
            field.state_set(model)
            if not field.get_state_attrs(model).get('valid', True):
                cell.set_property('background',
                        COLORS.get('invalid', 'white'))
            elif bool(int(field.get_state_attrs(model).get('required', 0))):
                cell.set_property('background',
                        COLORS.get('required', 'white'))
            else:
                cell.set_property('background', 'white')
            readonly = field.get_state_attrs(model).get('readonly', False)
            if isinstance(cell, gtk.CellRendererToggle):
                cell.set_property('activatable', not readonly)
            elif isinstance(cell,
                    (gtk.CellRendererProgress, CellRendererButton)):
                pass
            else:
                cell.set_property('editable', not readonly)
        cell.set_property('xalign', align)

    def get_color(self, model):
        to_display = ''
        for color, expr in self.treeview.colors.items():
            if model.expr_eval(expr, check_load=False):
                to_display = color
                break
        return to_display or 'black'

    def open_remote(self, model, create, changed=False, text=None):
        raise NotImplementedError

    def get_textual_value(self, model):
        return model[self.field_name].get_client(model) or ''

    def value_from_text(self, model, text):
        return text

class Int(Char):

    def value_from_text(self, model, text):
        return int(text)

    def get_textual_value(self, model):
        return locale.format('%d',
                model[self.field_name].get_client(model) or 0, True)

class Boolean(Int):

    def __init__(self, *args):
        super(Boolean, self).__init__(*args)
        self.renderer = gtk.CellRendererToggle()
        self.renderer.connect('toggled', self._sig_toggled)

    def get_textual_value(self, model):
        return model[self.field_name].get_client(model)

    def setter(self, column, cell, store, iter):
        model = store.get_value(iter, 0)
        value = self.get_textual_value(model)
        cell.set_active(bool(value))

    def _sig_toggled(self, renderer, path):
        store = self.treeview.get_model()
        model = store.get_value(store.get_iter(path), 0)
        field = model[self.field_name]
        if not field.get_state_attrs(model).get('readonly', False):
            value = model[self.field_name].get_client(model)
            model[self.field_name].set_client(model, int(not value))
            self.treeview.set_cursor(path)
        return True


class Date(Char):
    server_format = DT_FORMAT
    display_format = date_format()

    def __init__(self, field_name, model, treeview=None, attrs=None,
            window=None):
        self.field_name = field_name
        self.model = model
        self.attrs = attrs or {}
        self.renderer = CellRendererDate(self.display_format)
        self.treeview = treeview
        self.window = window

    def get_textual_value(self, model):
        value = model[self.field_name].get_client(model)
        if not value:
            return ''
        date = mx.DateTime.strptime(value, self.server_format)
        return date.strftime(self.display_format)

    def value_from_text(self, model, text):
        if not text:
            return False
        try:
            date = mx.DateTime.strptime(text, self.display_format)
        except:
            return False
        return date.strftime(self.server_format)


class Datetime(Date):
    server_format = DHM_FORMAT
    display_format = date_format() + ' ' + HM_FORMAT

    def get_textual_value(self, model):
        value = model[self.field_name].get_client(model)
        if not value:
            return ''
        date = mx.DateTime.strptime(value, self.server_format)
        if 'timezone' in rpc.CONTEXT:
            try:
                import pytz
                lzone = pytz.timezone(rpc.CONTEXT['timezone'])
                szone = pytz.timezone(rpc.TIMEZONE)
                datetime = DT.datetime(date.year, date.month, date.day,
                        date.hour, date.minute, int(date.second))
                sdt = szone.localize(datetime, is_dst=True)
                ldt = sdt.astimezone(lzone)
                date = mx.DateTime.DateTime(*(ldt.timetuple()[:6]))
            except:
                pass
        return date.strftime(self.display_format)

    def value_from_text(self, model, text):
        if not text:
            return False
        try:
            date = mx.DateTime.strptime(text, self.display_format)
        except:
            return False
        if 'timezone' in rpc.CONTEXT:
            try:
                import pytz
                lzone = pytz.timezone(rpc.CONTEXT['timezone'])
                szone = pytz.timezone(rpc.TIMEZONE)
                datetime = DT.datetime(date.year, date.month, date.day,
                        date.hour, date.minute, int(date.second))
                ldt = lzone.localize(datetime, is_dst=True)
                sdt = ldt.astimezone(szone)
                date = mx.DateTime.DateTime(*(sdt.timetuple()[:6]))
            except:
                pass
        return date.strftime(self.server_format)

class Float(Char):
    def get_textual_value(self, model):
        if isinstance(self.attrs.get('digits'), str):
            digit = model.expr_eval(self.attrs['digits'])[1]
        else:
            digit = self.attrs.get('digits', (16, 2))[1]
        return locale.format('%.'+str(digit)+'f',
                model[self.field_name].get_client(model) or 0.0, True)

    def value_from_text(self, model, text):
        try:
            return locale.atof(text)
        except:
            return 0.0


class FloatTime(Char):

    def get_textual_value(self, model):
        val = model[self.field_name].get_client(model)
        value = '%02d:%02d' % (math.floor(abs(val)),
                round(abs(val) % 1 + 0.01, 2) * 60)
        if val < 0:
            value = '-' + value
        return value

    def value_from_text(self, model, text):
        try:
            if text and ':' in text:
                # assume <hours>:<minutes>
                h, m = text.split(':')
                h = h or 0
                m = m or 0
                return round(int(h) + int(m)/60.0, 2)
            else:
                # try float in locale notion
                return locale.atof(text)
        except:
            return 0.0

class M2O(Char):

    def value_from_text(self, model, text):
        if not text:
            return False

        relation = model[self.field_name].attrs['relation']
        rpc_relation = RPCProxy(relation)

        domain = model[self.field_name].domain_get(model)
        context = model[self.field_name].context_get(model)

        try:
            names = rpc_relation.name_search(text, domain, 'ilike', context)
        except Exception, exception:
            common.process_exception(exception, self.window)
            return '???'
        if len(names) != 1:
            return self.search_remote(relation, [x[0] for x in names],
                             domain=domain, context=context)[0]
        return names[0]

    def open_remote(self, model, create=True, changed=False, text=None):
        modelfield = model.mgroup.mfields[self.field_name]
        relation = modelfield.attrs['relation']

        domain = modelfield.domain_get(model)
        context = modelfield.context_get(model)
        if create:
            obj_id = None
        elif not changed:
            obj_id = modelfield.get(model)
        else:
            rpc_relation = RPCProxy(relation)

            try:
                names = rpc_relation.name_search(text, domain, 'ilike', context)
            except Exception, exception:
                common.process_exception(exception, self.window)
                return False, False
            if len(names) == 1:
                return True, names[0]
            searched = self.search_remote(relation, [x[0] for x in names],
                    domain=domain, context=context)
            if searched[0]:
                return True, searched
            return False, False
        dia = M2ODialog(relation, obj_id, domain=domain, context=context,
                window=self.window)
        res, value = dia.run()
        dia.destroy()
        if res:
            return True, value
        else:
            return False, False

    def search_remote(self, relation, ids=None, domain=None, context=None):
        rpc_relation = RPCProxy(relation)

        win = WinSearch(relation, sel_multi=False, ids=ids, context=context,
                domain=domain, parent=self.window)
        found = win.run()
        if found:
            try:
                return rpc_relation.name_get([found[0]], context)[0]
            except Exception, exception:
                common.process_exception(exception, self.window)
                return False, None
        else:
            return False, None

class UnsettableColumn(Exception):

    def __init__(self):
        Exception.__init__()


class O2M(Char):

    def setter(self, column, cell, store, iter):
        super(O2M, self).setter(column, cell, store, iter)
        cell.set_property('xalign', 0.5)

    def get_textual_value(self, model):
        return '( ' + str(len(model[self.field_name].\
                get_client(model).models)) + ' )'

    def value_from_text(self, model, text):
        pass

    def open_remote(self, model, create=True, changed=False, text=None):
        models = model.value[self.field_name]
        modelfield = model.mgroup.mfields[self.field_name]
        relation = modelfield.attrs['relation']
        context = modelfield.context_get(model)

        dia = O2MDialog(relation, parent=model, model=models,
                attrs=modelfield.attrs, default_get_ctx=context,
                window=self.window)
        res, value = dia.run()
        dia.destroy()
        return False, False


class M2M(Char):

    def setter(self, column, cell, store, iter):
        super(M2M, self).setter(column, cell, store, iter)
        cell.set_property('xalign', 0.5)

    def get_textual_value(self, model):
        value = model[self.field_name].get_client(model)
        if value:
            return '(%s)' % len(value)
        else:
            return '(0)'

    def value_from_text(self, model, text):
        if not text:
            return []
        if not (text[0] != '('):
            return model[self.field_name].get(model)
        relation = model[self.field_name].attrs['relation']
        rpc_relation = RPCProxy(relation)
        domain = model[self.field_name].domain_get(model)
        context = model[self.field_name].context_get(model)
        try:
            names = rpc_relation.name_search(text, domain, 'ilike', context)
        except Exception, exception:
            common.process_exception(exception, self.window)
            return []
        ids = [x[0] for x in names]
        win = WinSearch(relation, sel_multi=True, ids=ids, context=context,
                domain=domain)
        found = win.go()
        return found or []

    def open_remote(self, model, create=True, changed=False, text=None):
        modelfield = model[self.field_name]
        relation = modelfield.attrs['relation']

        rpc_relation = RPCProxy(relation)
        context = model[self.field_name].context_get(model)
        domain = model[self.field_name].domain_get(model)
        if create:
            if text and len(text) and text[0] != '(':
                domain.append(('name', '=', text))
            try:
                ids = rpc_relation.search(domain)
            except Exception, exception:
                common.process_exception(exception, self.window)
                return False, None
            if ids and len(ids)==1:
                return True, ids
        else:
            ids = model[self.field_name].get_client(model)
        win = WinSearch(relation, sel_multi=True, ids=ids, context=context,
                domain=domain)
        found = win.go()
        if found:
            return True, found
        else:
            return False, None

class Selection(Char):

    def __init__(self, *args):
        super(Selection, self).__init__(*args)
        self.renderer = gtk.CellRendererCombo()
        selection_data = gtk.ListStore(str, str)
        selection = self.attrs.get('selection', [])
        if 'relation' in self.attrs:
            try:
                selection = rpc.execute('object', 'execute',
                        self.attrs['relation'], 'name_search', '',
                        self.attrs.get('domain', []), 'ilike', rpc.CONTEXT)
            except Exception, exception:
                common.process_exception(exception, self.window)
                selection = []
        else:
            if not isinstance(selection, (list, tuple)):
                try:
                    selection = rpc.execute('object', 'execute',
                            self.model, selection, rpc.CONTEXT)
                except Exception, exception:
                    common.process_exception(exception, self.window)
                    selection = []
        if self.attrs.get('sort', True):
            selection.sort(lambda x, y: cmp(x[1], y[1]))
        self.attrs['selection'] = selection
        self.selection = selection
        for i in self.selection:
            selection_data.append(i)
        self.renderer.set_property('model', selection_data)
        self.renderer.set_property('text-column', 1)

    def get_textual_value(self, model):
        value = model[self.field_name].get(model)
        if isinstance(value, (list, tuple)):
            value = value[0]
        return dict(self.selection).get(value, '')

    def value_from_text(self, model, text):
        res = False
        for val, txt in self.selection:
            if txt[:len(text)].lower() == text.lower():
                if len(txt) == len(text):
                    return val
                res = val
        return res


class Reference(Char):

    def __init__(self, field_name, model, treeview=None, attrs=None,
            window=None):
        super(Reference, self).__init__(field_name, model, treeview=treeview,
                attrs=attrs, window=window)
        self._selection = {}
        selection = attrs.get('selection', [])
        if not isinstance(selection, (list, tuple)):
            try:
                selection = rpc.execute('object', 'execute',
                        model, selection, rpc.CONTEXT)
            except Exception, exception:
                common.process_exception(exception, self.window)
                selection = []
        selection.sort(lambda x, y: cmp(x[1], y[1]))
        for i, j in selection:
            self._selection[i] = str(j)

    def get_textual_value(self, model):
        value = model[self.field_name].get_client(model)
        if not value:
            model, (obj_id, name) = '', (0, '')
        else:
            model, obj_id = value
            name = ''
            if isinstance(obj_id, (list, tuple)):
                obj_id, name = obj_id
        if model:
            if not name and obj_id:
                try:
                    obj_id, name = RPCProxy(model).name_get(obj_id,
                            rpc.CONTEXT)[0]
                except Exception, exception:
                    common.process_exception(exception, self.window)
                    name = '???'
            return self._selection[model] + ',' + name
        else:
            return ''

    def value_from_text(self, model, text):
        pass


class ProgressBar(object):
    orientations = {
        'left_to_right': gtk.PROGRESS_LEFT_TO_RIGHT,
        'right_to_left': gtk.PROGRESS_RIGHT_TO_LEFT,
        'bottom_to_top': gtk.PROGRESS_BOTTOM_TO_TOP,
        'top_to_bottom': gtk.PROGRESS_TOP_TO_BOTTOM,
    }

    def __init__(self, field_name, model, treeview=None, attrs=None, window=None):
        self.field_name = field_name
        self.model = model
        self.attrs = attrs or {}
        self.renderer = gtk.CellRendererProgress()
        orientation = self.orientations.get(self.attrs.get('orientation',
            'left_to_right'), gtk.PROGRESS_LEFT_TO_RIGHT)
        self.renderer.set_property('orientation', orientation)
        self.treeview = treeview
        self.window = window

    def setter(self, column, cell, store, iter):
        model = store.get_value(iter, 0)
        value = float(self.get_textual_value(model) or 0.0)
        cell.set_property('value', value)
        if isinstance(self.attrs.get('digits'), str):
            digit = model.expr_eval(self.attrs['digits'])[1]
        else:
            digit = self.attrs.get('digits', (16, 2))[1]
        text = locale.format('%.' + str(digit) + 'f', value, True)
        cell.set_property('text', text + '%')

    def open_remote(self, model, create, changed=False, text=None):
        raise NotImplementedError

    def get_textual_value(self, model):
        return model[self.field_name].get_client(model) or ''

    def value_from_text(self, model, text):
        return float(text)


class Button(object):

    def __init__(self, treeview=None, attrs=None, window=None, screen=None):
        super(Button, self).__init__()
        self.attrs = attrs or {}
        self.renderer = CellRendererButton(attrs.get('string', _('Unknown')))
        self.treeview = treeview
        self.window = window
        self.screen = screen

        self.renderer.connect('clicked', self.button_clicked)

    def button_clicked(self, widget, path):
        if not path:
            return True
        store = self.treeview.get_model()
        model = store.get_value(store.get_iter(path), 0)

        state_changes = self.attrs.get('states', {})
        if isinstance(state_changes, basestring):
            state_changes = eval(state_changes)
        if 'invisible' in state_changes:
            if model.expr_eval(state_changes['invisible'], check_load=False):
                return True
        if 'readonly' in state_changes:
            if model.expr_eval(state_changes['readonly'], check_load=False):
                return True

        self.screen.current_model = model
        obj_id = self.screen.save_current()
        if obj_id:
            if not self.attrs.get('confirm', False) or \
                    common.sur(self.attrs['confirm'], self.window):
                button_type = self.attrs.get('type', 'workflow')
                if button_type == 'workflow':
                    args = ('object', 'exec_workflow', self.screen.name,
                            self.attrs['name'], obj_id)
                    try:
                        rpc.execute(*args)
                    except Exception, exception:
                        common.process_exception(exception, self.window, *args)
                elif button_type == 'object':
                    args = ('object', 'execute', self.screen.name,
                            self.attrs['name'], [obj_id], model.context_get())
                    try:
                        rpc.execute(*args)
                    except Exception, exception:
                        common.process_exception(exception, self.window, *args)
                elif button_type == 'action':
                    action_id = None
                    args = ('object', 'execute', 'ir.action', 'get_action_id',
                            int(self.attrs['name']), rpc.CONTEXT)
                    try:
                        action_id = rpc.execute(*args)
                    except Exception, exception:
                        action_id = common.process_exception(exception,
                                self.window, *args)
                    if action_id:
                        Action.execute(action_id, {
                            'model': self.screen.name,
                            'id': obj_id,
                            'ids': [obj_id],
                            }, self.window)
                else:
                    raise Exception('Unallowed button type')
                self.screen.reload()
            else:
                if self.screen.form:
                    self.screen.form.message_info(
                            _('Invalid Form, correct red fields!'))
                self.screen.display()

CELLTYPES = {
    'char': Char,
    'many2one': M2O,
    'date': Date,
    'one2many': O2M,
    'many2many': M2M,
    'selection': Selection,
    'float': Float,
    'numeric': Float,
    'float_time': FloatTime,
    'integer': Int,
    'datetime': Datetime,
    'boolean': Boolean,
    'text': Char,
    'url': Char,
    'email': Char,
    'callto': Char,
    'sip': Char,
    'progressbar': ProgressBar,
    'reference': Reference,
}
