from odoo import fields, models, api


class HospitalAppointment(models.Model):
    _name = 'hospital.appointment'
    _inherit = ['mail.thread']
    _description = 'Hospital Appointment'
    _rec_names_search = ['reference', 'patient_id']
    _rec_name = 'patient_id'

    reference = fields.Char(string='Reference', default='New')
    #ondelete="restrict" doesn't allow you to delete if your field is related to an other field in an other module
    #ondelete="cascade" delete the field and every field related to it
    #ondelete="set null" delete the field and turn null to any reference in any other module required should be False
    patient_id = fields.Many2one('hospital.patient', string='Patient', required=True, ondelete='restrict')
    date_appointment = fields.Date(string='Time')
    note = fields.Text(string='Note')

    state = fields.Selection(
        [('draft','Draft'),('confirmed','Confirmed'),('ongoing','Ongoing'),
         ('done','Done'),('canceled','Canceled')],default='draft',tracking=True)

    appointment_line_ids = fields.One2many('hospital.appointment.lines','appointment_id', string='Lines')
    # store=True to store the total_qty fields in the database
    # total_qty = fields.Float(compute='_compute_total_qty', string='Total Quantity', store=True)
    total_qty = fields.Float(compute='_compute_total_qty', string='Total Quantity')
    #related fields
    #also you remove string='DOB' and you can add store=True if you want to store the data in DB
    date_of_birth = fields.Date(string='DOB', related='patient_id.date_of_birth')
    #groups="om__hospital.group_hospital_doctors" only doctors can see this field
    @api.model_create_multi
    def create(self, vals_list):
        print("odoo mates", vals_list)
        for vals in vals_list:
            if not vals.get('reference') or vals['reference'] == 'New':
                vals['reference'] = self.env['ir.sequence'].next_by_code('hospital.appointment')
        return super().create(vals_list)
    #It tells Odoo that the _compute_total_qty method (which computes the value of total_qty) should be re-executed whenever:
    #The appointment_line_ids field changes (e.g., new lines are added or removed).
    #The qty field of any record in appointment_line_ids is modified.
    @api.depends('appointment_line_ids','appointment_line_ids.qty')
    #@api.onchange() use only simple field meaning that it accept only view field of the same model not for relational fields pseudo fields
    def _compute_total_qty(self):
        for rec in self:
            #total_qty = 0
            #for line in rec.appointment_line_ids:
            #    total_qty += line.qty
            #rec.total_qty = total_qty
            #instead we ca n use this :
            rec.total_qty = sum(rec.appointment_line_ids.mapped('qty'))
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f"[{rec.reference}] {rec.patient_id.name}"
    def action_confirm(self):
        for rec in self:
            rec.state='confirmed'
    def action_done(self):
        for rec in self:
            rec.state='done'
    def action_cancel(self):
        for rec in self:
            rec.state='canceled'
    def action_ongoing(self):
        for rec in self:
            rec.state='ongoing'
class HospitalAppointmentLines(models.Model):
    _name = 'hospital.appointment.lines'
    _description = 'Hospital Appointment Lines'

    appointment_id = fields.Many2one('hospital.appointment', string='Appointment')
    product_id = fields.Many2one('product.product', string='Product')
    qty = fields.Float(string='Quantity')
