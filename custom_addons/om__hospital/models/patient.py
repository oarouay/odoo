from odoo  import fields, models,_,api
from odoo.exceptions import UserError, ValidationError


class HospitalPatient(models.Model):
    _name = 'hospital.patient'
    _inherit = ['mail.thread']
    _description = 'Patient Master'

    name =fields.Char(string='Name',required=True, tracking=True)
    date_of_birth = fields.Date(string='DOB', tracking=True)
    gender = fields.Selection([('male', 'Male'), ('female', 'Female')],string = 'Gender')
    # these are optional 'patient_tag_rel','patient_id','tag_id'if you don't put them its okay odoo will take care of it
    tag_ids = fields.Many2many('patient.tag', 'patient_tag_rel','patient_id','tag_id',string='Tags')

    is_minor = fields.Boolean(string='Minor')
    guardian = fields.Char(string='Guardian')
    weight = fields.Float(string='Weight')

    #this will execute on the deletion of a record
    #the decorator @api.ondelete helps us do that
    @api.ondelete(at_uninstall=False)
    def _check_patient_appointments(self):
         for rec in self:
             domain = [('patient_id', '=', rec.id)]
             appointments = self.env['hospital.appointment'].search(domain)
             if appointments:
                 raise ValidationError(_("You cannot delete the patient now.\nThis patient has existing appointments"
                                         "\n Patient name : %s" % rec.name))

    #this execute upon the deletion of a patient
    # def unlink(self):
    #     for rec in self:
    #         domain = [('patient_id', '=', rec.id)]
    #         appointments = self.env['hospital.appointment'].search(domain)
    #         if appointments:
    #             raise ValidationError(_("You cannot delete the patient now.\nThis patient has existing appointments"
    #                                     "\n Patient name : %s" % rec.name))
    #     return super().unlink()
