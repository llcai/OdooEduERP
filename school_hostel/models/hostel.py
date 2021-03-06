# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.

from lxml import etree
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from dateutil.relativedelta import relativedelta as rd
from datetime import datetime
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT


class ResPartner(models.Model):
    _inherit = "res.partner"

    is_hostel_rector = fields.Boolean('Hostel Rector')


class HostelType(models.Model):
    _name = 'hostel.type'

    name = fields.Char('HOSTEL Name', required=True,
                       help="Name of Hostel")
    type = fields.Selection([('male', 'Boys'), ('female', 'Girls'),
                             ('common', 'Common')], 'HOSTEL Type',
                            help="Type of Hostel",
                            required=True, default='common')
    other_info = fields.Text('Other Information')
    rector = fields.Many2one('res.partner', 'Rector')
    room_ids = fields.One2many('hostel.room', 'name', 'Room')
    student_ids = fields.One2many('hostel.student', 'hostel_info_id',
                                  string='Students')

    @api.model
    def _search(self, args, offset=0, limit=None, order=None, count=False,
                access_rights_uid=None):
        '''Override method to get hostel of student selected'''
        if self._context.get('student_id'):
            stud_obj = self.env['student.student']
            stud = stud_obj.browse(self._context['student_id'])
            datas = []
            if stud.gender:
                self._cr.execute("""select id from hostel_type where type=%s or
                type='common' """, (stud.gender,))
                data = self._cr.fetchall()
                for d in data:
                    datas.append(d[0])
            args.append(('id', 'in', datas))
        return super(HostelType, self)._search(
            args=args, offset=offset, limit=limit, order=order, count=count,
            access_rights_uid=access_rights_uid)


class HostelRoom(models.Model):

    _name = 'hostel.room'
    _rec_name = 'room_no'

    @api.model
    def fields_view_get(self, view_id=None, view_type='form', toolbar=False,
                        submenu=False):
        res = super(HostelRoom, self).fields_view_get(view_id=view_id,
                                                      view_type=view_type,
                                                      toolbar=toolbar,
                                                      submenu=submenu)
        user_group = self.env.user.has_group('school_hostel.group_hostel_user')
        doc = etree.XML(res['arch'])
        if user_group:
            if view_type == 'tree':
                nodes = doc.xpath("//tree[@name='hostel_room']")
                for node in nodes:
                    node.set('edit', 'false')
                res['arch'] = etree.tostring(doc)
            if view_type == 'form':
                nodes = doc.xpath("//form[@name='hostel_room']")
                for node in nodes:
                    node.set('edit', 'false')
                res['arch'] = etree.tostring(doc)
        return res

    @api.depends('student_per_room', 'student_ids')
    def _compute_check_availability(self):
        '''Method to check room availability'''
        room_availability = 0
        for data in self:
            count = 0
            if data.student_ids:
                count += 1
            room_availability = data.student_per_room - len(
                data.student_ids.ids)
            data.availability = room_availability

    name = fields.Many2one('hostel.type', 'HOSTEL',
                           help="Name of hostel")
    floor_no = fields.Integer('Floor No.', default=1,
                              help="Floor Number")
    room_no = fields.Char('Room No.', required=True)
    student_per_room = fields.Integer('Student Per Room', required=True,
                                      help="Students allocated per room")
    availability = fields.Float(compute='_compute_check_availability',
                                store=True, string="Availability")
    telephone = fields.Boolean('Telephone access')
    rent_amount = fields.Float('Rent Amount Per Month')
    ac = fields.Boolean('Air Conditioning')
    private_bathroom = fields.Boolean('Private Bathroom')
    guest_sofa = fields.Boolean('Guest sofa-bed')
    tv = fields.Boolean('Television')
    internet = fields.Boolean('Internet Access')
    refrigerator = fields.Boolean('Refrigerator')
    microwave = fields.Boolean('Microwave')
    student_ids = fields.One2many('hostel.student', 'room_id',
                                  string="Students")

    _sql_constraints = [('room_no_unique', 'unique(room_no)',
                         'Room number must be unique!')]
    _sql_constraints = [('floor_per_hostel', 'check(floor_no < 10)',
                         'Error ! Floor per HOSTEL should be less than 10.')]
    _sql_constraints = [('student_per_room_greater',
                         'check(student_per_room < 10)',
                         'Error ! Student per room should be less than 10.')]


class HostelStudent(models.Model):
    _name = 'hostel.student'
    _rec_name = 'student_id'

    @api.depends('room_rent', 'paid_amount')
    def _compute_remaining_fee_amt(self):
        '''Method to compute hostel amount'''
        for rec in self:
            rec.remaining_amount = rec.room_rent - (rec.paid_amount or 0.0)

    @api.constrains('duration')
    def check_duration(self):
        '''Method to check duration should be greater than zero'''
        if self.duration <= 0:
            raise ValidationError(_('Duration should be greater than 0!'))

    @api.multi
    def _compute_invoices(self):
        '''Method to compute number of invoice of student'''
        inv_obj = self.env['account.invoice']
        for rec in self:
            rec.compute_inv = inv_obj.search_count([('hostel_student_id', '=',
                                                     rec.id)])

    @api.depends('duration')
    def _compute_rent(self):
        '''Method to compute hostel room rent'''
        for rec in self:
            amt = rec.room_id.rent_amount or 0.0
            rec.room_rent = rec.duration * amt

    @api.onchange('hostel_info_id')
    def onchange_hostel(self):
        '''Method to make room false when hostel changes'''
        self.room_id = False

    @api.constrains('room_id')
    def check_room_avaliable(self):
        '''Check Room Availability'''
        if self.room_id.availability <= 0:
                raise ValidationError(_('''There is no avalilability in the
                room!'''))

    @api.multi
    def unlink(self):
        for rec in self:
            if rec.status in ['reservation', 'pending', 'paid']:
                raise ValidationError(_('''You can delete record in
                unconfirm state only!'''))
        return super(HostelStudent, self).unlink()

    @api.depends('status')
    def _get_hostel_user(self):
        user_group = self.env.ref('school_hostel.group_hostel_user')
        grps = [group.id
                for group in self.env['res.users'].browse(self._uid).groups_id]
        if user_group.id in grps:
            self.hostel_user = True

    hostel_id = fields.Char('HOSTEL ID', readonly=True,
                            default=lambda self: _('New'))
    compute_inv = fields.Integer('Number of invoice',
                                 compute="_compute_invoices")
    student_id = fields.Many2one('student.student', 'Student')
    school_id = fields.Many2one('school.school', 'School')
    room_rent = fields.Float('Total Room Rent', compute="_compute_rent",
                             required=True,
                             help="Rent of room")
#    bed_type = fields.Many2one('bed.type', 'Bed Type')
    admission_date = fields.Datetime('Admission Date',
                                     help="Date of admission in hostel",
                                     default=fields.Date.context_today)
    discharge_date = fields.Datetime('Discharge Date',
                                     help="Date on which student discharge")
    paid_amount = fields.Float('Paid Amount',
                               help="Amount Paid")
    hostel_info_id = fields.Many2one('hostel.type', "Hostel")
    room_id = fields.Many2one('hostel.room', "Room")
    duration = fields.Integer('Duration')
    rent_pay = fields.Float('Rent')
    acutal_discharge_date = fields.Datetime('Actual Discharge Date',
                                            help='''Date on which student
                                            discharge''')
    remaining_amount = fields.Float(compute='_compute_remaining_fee_amt',
                                    string='Remaining Amount')
    status = fields.Selection([('draft', 'Draft'),
                               ('reservation', 'Reservation'),
                               ('pending', 'Pending'),
                               ('paid', 'Done'),
                               ('discharge', 'Discharge'),
                               ('cancel', 'Cancel')],
                              string='Status',
                              default='draft')
    hostel_types = fields.Char('Type')
    stud_gender = fields.Char('Gender')

    _sql_constraints = [('admission_date_greater',
                         'check(discharge_date >= admission_date)',
                         'Error ! Discharge Date cannot be set'
                         'before Admission Date.')]

    @api.multi
    def cancel_state(self):
        '''Method to change state to cancel'''
        for rec in self:
            rec.status = 'cancel'
            # increase room availability
            rec.room_id.availability += 1
        return True

    @api.onchange('hostel_info_id')
    def onchange_hostel_types(self):
        self.hostel_types = self.hostel_info_id.type

    @api.onchange('student_id')
    def onchange_student_gender(self):
        '''Method to get gender of student'''
        self.stud_gender = self.student_id.gender

    @api.multi
    def reservation_state(self):
        '''Method to change state to reservation'''
        for rec in self:
            if rec.hostel_id == 'New':
                rec.hostel_id = self.env['ir.sequence'
                                         ].next_by_code('hostel.student'
                                                        ) or _('New')
            rec.status = 'reservation'
        return True

    @api.multi
    @api.onchange('admission_date', 'duration')
    def onchnage_discharge_date(self):
        '''to calculate discharge date based on current date and duration'''
        if self.admission_date:
            date = datetime.strptime(self.admission_date,
                                     DEFAULT_SERVER_DATETIME_FORMAT)
            self.discharge_date = date + rd(months=self.duration)

    @api.model
    def create(self, vals):
        res = super(HostelStudent, self).create(vals)
        date = datetime.strptime(res.admission_date,
                                 DEFAULT_SERVER_DATETIME_FORMAT)
        res.discharge_date = date + rd(months=res.duration)
        vals.update({'discharge_date': res.discharge_date,
                     })
        return res

    @api.multi
    def write(self, vals):
        duration_months = vals.get('duration') or self.duration
        addmissiondate = vals.get('admission_date') or self.admission_date
        if addmissiondate and not vals.get('discharge_date'):
            date = datetime.strptime(addmissiondate,
                                     DEFAULT_SERVER_DATETIME_FORMAT)
            discharge_date_student = date + rd(months=duration_months)
            vals.update({'discharge_date': discharge_date_student,
                         })
        return super(HostelStudent, self).write(vals)

    @api.constrains('student_id')
    def check_student_registration(self):
        student = self.search([('student_id', '=', self.student_id.id),
                               ('id', 'not in', self.ids)])
        if student:
            raise ValidationError(_('''Selected student is already
            registered!'''))

    @api.multi
    def discharge_state(self):
        '''Method to change state to discharge'''
        curr_date = datetime.now()
        for rec in self:
            rec.status = 'discharge'
            rec.room_id.availability -= 1
            # set discharge date equal to current date
            rec.acutal_discharge_date = curr_date

    @api.multi
    def student_expire(self):
        ''' Schedular to discharge student from hostel'''
        current_date = datetime.now()
        new_date = current_date.strftime('%m-%d-%Y')
        domian = [('discharge_date', '<', new_date),
                  ('status', '!=', 'draft')]
        student_hostel = self.env['hostel.student'].search(domian)
        if student_hostel:
            for student in student_hostel:
                student.write({'status': 'discharge'})
                student.discharge_state()
        return True

    @api.multi
    def invoice_view(self):
        '''Method to view number of invoice of student'''
        invoice_obj = self.env['account.invoice']
        for rec in self:
            invoices = invoice_obj.search([('hostel_student_id', '=', rec.id)
                                           ])
            action = rec.env.ref('account.action_invoice_tree1').read()[0]
            if len(invoices) > 1:
                action['domain'] = [('id', 'in', invoices.ids)]
            elif len(invoices) == 1:
                action['views'] = [(rec.env.ref('account.invoice_form').id,
                                    'form')]
                action['res_id'] = invoices.ids[0]
            else:
                action = {'type': 'ir.actions.act_window_close'}
        return action

    @api.multi
    def pay_fees(self):
        '''Method generate invoice of hostel fees of student'''
        invoice_obj = self.env['account.invoice']
        for rec in self:
            rec.write({'status': 'pending'})
            partner = rec.student_id and rec.student_id.partner_id
            vals = {'partner_id': partner.id,
                    'account_id': partner.property_account_receivable_id.id,
                    'hostel_student_id': rec.id,
                    'hostel_ref': rec.hostel_id}
            account_inv_id = invoice_obj.create(vals)
            acc_id = account_inv_id.journal_id.default_credit_account_id.id
            account_view_id = rec.env.ref('account.invoice_form')
            invoice_lines = []
            line_vals = {'name': rec.hostel_info_id.name,
                         'account_id': acc_id,
                         'quantity': rec.duration,
                         'price_unit': rec.room_id.rent_amount}
            invoice_lines.append((0, 0, line_vals))
            account_inv_id.write({'invoice_line_ids': invoice_lines})
            return {'name': _("Pay Hostel Fees"),
                    'view_type': 'form',
                    'view_mode': 'form',
                    'res_model': 'account.invoice',
                    'view_id': account_view_id.id,
                    'type': 'ir.actions.act_window',
                    'nodestroy': True,
                    'target': 'current',
                    'res_id': account_inv_id.id,
                    'context': {}}

    @api.multi
    def print_fee_receipt(self):
        '''Method to print fee reciept'''
        return self.env['report'
                        ].get_action(self,
                                     'school_hostel.hostel_fee_reciept1')


class AccountInvoice(models.Model):

    _inherit = "account.invoice"

    hostel_student_id = fields.Many2one('hostel.student',
                                        string="Hostel Student")
    hostel_ref = fields.Char('Hostel Fees Reference',
                             help="Hostel Fee Reference")


class AccountPayment(models.Model):
    _inherit = "account.payment"

    @api.multi
    def post(self):
        res = super(AccountPayment, self).post()
        for rec in self:
            for inv in rec.invoice_ids:
                vals = {}
                if inv.hostel_student_id and inv.state == 'paid':
                    fees_payment = (inv.hostel_student_id.paid_amount +
                                    rec.amount)
                    vals.update({'status': 'paid',
                                 'paid_amount': fees_payment})
                    inv.hostel_student_id.write(vals)
                elif inv.hostel_student_id and inv.state == 'open':
                    fees_payment = (inv.hostel_student_id.paid_amount +
                                    rec.amount)
                    vals.update({'status': 'pending',
                                 'paid_amount': fees_payment,
                                 'remaining_amount': inv.residual})
                inv.hostel_student_id.write(vals)
        return res
