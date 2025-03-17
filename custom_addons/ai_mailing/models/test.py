import json
from requests_oauthlib import OAuth1
from odoo import models, fields, api
from dotenv import load_dotenv
import os
from datetime import datetime
import requests


class SocialEmail(models.Model):
    _name = 'social.email'
    _description = 'Social Email'
    _inherit = ['mail.thread']

    name = fields.Char(string="Email Subject", required=True)
    content = fields.Html(string="Content", sanitize=False)  # Prevent sanitization
    campaign_id = fields.Many2one('marketing.campaign', string='Campaign')
    is_published = fields.Boolean(string="Is Published", default=False)
    mail_scheduling_status = fields.Selection([
        ('draft', 'Draft'),
        ('scheduled', 'Scheduled for Sending'),
        ('sent', 'Sent'),
        ('failed', 'Sending Failed')
    ], string="Scheduling Status", default='draft')
    recipient_ids = fields.Many2many(
        'res.partner',
        string="Recipients",
        domain="[('email', '!=', False)]"
    )
    email_addresses = fields.Char(string="Email Addresses", compute="_compute_email_addresses", store=True,
                                  readonly=True)
    publish_date = fields.Datetime(string="Publish Date")
    mailing_id = fields.Many2one('mailing.mailing', string='Mass Mailing', ondelete='set null')

    @api.depends("recipient_ids.email")
    def _compute_email_addresses(self):
        for record in self:
            record.email_addresses = ', '.join(record.recipient_ids.mapped('email'))

    def _get_personalized_body(self, partner):
        """Replace {{name}} in the email body with the recipient's name."""
        if self.content:
            return self.content.replace("{{name}}", partner.name or "Valued Customer")
        return ""

    def action_confirm(self):
        """Mark message as scheduled and create mass mailing"""
        self.ensure_one()
        mailing_model = self.env['ir.model']._get('res.partner').id

        # Create a single mailing record with all recipients
        vals = {
            'subject': self.name,
            'body_html': self.content,
            'mailing_model_id': mailing_model,
            'mailing_domain': [('id', 'in', self.recipient_ids.ids)],
            'reply_to_mode': 'new',
            'schedule_date': self.publish_date,
            'state': 'draft',
        }

        mailing = self.env['mailing.mailing'].create(vals)
        self.write({
            'mailing_id': mailing.id,
            'mail_scheduling_status': 'scheduled'
        })

        self.message_post(body=f"Email scheduled for {self.publish_date}")

    @api.model
    def cron_check_status_emails(self):
        """Cron job to send scheduled emails using mailing.mailing."""
        now = fields.Datetime.now()
        emails = self.search([
            ('mail_scheduling_status', '=', 'scheduled'),
            ('publish_date', '<=', now)
        ])
        for email in emails:
            try:
                if not email.mailing_id:
                    raise ValueError("No mailing record found")

                # Put mailing in queue for sending
                email.mailing_id.action_put_in_queue()
                # Actually send the emails
                email.mailing_id.action_send_mail()
                email.write({'mail_scheduling_status': 'sent'})
                email.message_post(body="Email message queued for sending via mailing.mailing!")
            except Exception as e:
                email.write({'mail_scheduling_status': 'failed'})
                email.message_post(body=f"Failed to send Email: {str(e)}")

    def action_cancel(self):
        """Cancel a scheduled email"""
        if self.mailing_id:
            # Only delete if it's not already sent
            if self.mailing_id.state not in ['sending', 'done']:
                self.mailing_id.unlink()

        self.write({'mail_scheduling_status': 'draft'})
        self.message_post(body="Email scheduling cancelled")