from odoo import models, fields

class MailingMailing(models.Model):
    _inherit = 'mailing.mailing'

    social_email_id = fields.Many2one('social.email', string='Social Email', ondelete='cascade')