from odoo import models, fields, api
from dotenv import load_dotenv
import os
import requests


load_dotenv()

class SocialEmail(models.Model):
    _name = 'social.email'
    _description = 'Social Email'

    name = fields.Char(string="Email Subject", required=True)
    content = fields.Text(string="Content")
    campaign_id = fields.Many2one('marketing.campaign', string='Campaign')
    recipient_ids = fields.Many2many(
        'res.partner',
        string="Recipients",
        domain="[('email', '!=', False)]"
    )
    email_addresses = fields.Char(string="Email Addresses", compute="_compute_email_addresses", readonly=True)
    publish_date = fields.Datetime(string="Publish Date")

    @api.depends("recipient_ids")
    def _compute_email_addresses(self):
        for record in self:
            record.email_addresses = ', '.join(record.recipient_ids.mapped('email'))


class SocialWhatsApp(models.Model):
    _name = 'social.whatsapp'
    _description = 'Social WhatsApp Message'

    name = fields.Char(string="Message Title", required=True)
    message = fields.Text(string="Message")
    campaign_id = fields.Many2one('marketing.campaign', string='Campaign')
    recipient_ids = fields.Many2many(
        'res.partner',
        string="Recipients",
        domain="[('mobile', '!=', False)]"
    )
    phone_numbers = fields.Char(string="Phone Numbers", compute="_compute_phone_numbers", readonly=True)
    publish_date = fields.Datetime(string="Publish Date")

    @api.depends("recipient_ids")
    def _compute_phone_numbers(self):
        for record in self:
            record.phone_numbers = ', '.join(record.recipient_ids.mapped('mobile'))


class SocialInstagram(models.Model):
    _name = "social.instagram"
    _description = "Instagram Posts"

    name = fields.Char(string="Title")
    campaign_id = fields.Many2one('marketing.campaign', string='Campaign')
    # image = fields.Binary(string="Image")
    caption = fields.Text(string="Caption")
    publish_date = fields.Datetime(string="Publish Date")


class SocialFacebook(models.Model):
    _name = "social.facebook"
    _description = "Facebook Posts"
    _inherit = ["mail.thread"]

    name = fields.Char(string="Title")
    campaign_id = fields.Many2one('marketing.campaign', string='Campaign')
    content = fields.Text(string="Content")
    publish_date = fields.Datetime(string="Publish Date")

    scheduled_fb_post_id = fields.Char(string="Facebook Post ID", help="ID of the scheduled post on Facebook")
    fb_scheduling_status = fields.Selection([
        ('draft', 'Draft'),
        ('scheduled', 'Scheduled on Facebook'),
        ('published', 'Published'),
        ('failed', 'Scheduling Failed')
    ], string="Scheduling Status", default='draft')

    def action_confirm(self):
        for record in self:
            self.schedule_facebook_post(record,record.publish_date)

    def schedule_facebook_post(self, post_record, scheduled_date):
        """Schedule a post on Facebook using the Graph API."""
        try:
            # Facebook Graph API endpoint for scheduled posts
            graph_api_url = f"https://graph.facebook.com/v17.0/{os.getenv("PAGE_ID")}/feed"

            # Convert the datetime to Unix timestamp (seconds since epoch)
            scheduled_publish_time = int(scheduled_date.timestamp())
            print(scheduled_publish_time)

            # Prepare the post data
            payload = {
                'message': f"{self.name}\n\n{self.content}",
                'published': False,  # This makes it a scheduled post
                'scheduled_publish_time': scheduled_publish_time,
                'access_token':  os.getenv("ACCESS_TOKEN")
            }

            # If there's a media suggestion, we could potentially upload an image here
            # This would require additional code to either generate an image or use a stock image

            # Make the API request
            response = requests.post(graph_api_url, data=payload)
            response_data = response.json()
            print(response_data)
            if 'id' in response_data:
                # Update the post record with the Facebook post ID
                post_record.write({
                    'scheduled_fb_post_id': response_data['id'],
                    'fb_scheduling_status': 'scheduled'
                })
                self.message_post(body=f"Facebook post has been scheduled successfully for {scheduled_date}.")
                return True
            else:
                error_message = response_data.get('error', {}).get('message', 'Unknown error')
                post_record.write({'fb_scheduling_status': 'failed'})
                self.message_post(body=f"Failed to schedule Facebook post: {error_message}")
                return False

        except Exception as e:
            post_record.write({'fb_scheduling_status': 'failed'})
            self.message_post(body=f"Error scheduling Facebook post: {str(e)}")
            return False

    @api.onchange('scheduled_fb_post_id')
    def action_check_post_status(self):
        for record in self:

            url = f"https://graph.facebook.com/v17.0/{record.scheduled_fb_post_id}"
            params = {'access_token': os.getenv("ACCESS_TOKEN")}
            response = requests.get(url, params=params)
            data = response.json()

            if 'is_published' in data and data['is_published']:
                record.write({'fb_scheduling_status': 'published'})

            return {'type': 'ir.actions.client', 'tag': 'reload'}

        return True

    def action_cancel(self):
        for record in self:

            url = f"https://graph.facebook.com/v17.0/{record.scheduled_fb_post_id}"
            params = {'access_token': os.getenv("ACCESS_TOKEN")}
            response = requests.delete(url, params=params)

            if response.status_code in (200, 204):
                record.write({
                    'scheduled_fb_post_id': False,
                    'fb_scheduling_status': 'draft'
                })
                record.campaign_id.message_post(body="Scheduled Facebook post has been cancelled.")
            else:
                data = response.json()
                error_message = data.get('error', {}).get('message', 'Unknown error')
                record.campaign_id.message_post(body=f"Failed to cancel Facebook post: {error_message}")

            return {'type': 'ir.actions.client', 'tag': 'reload'}

        return True