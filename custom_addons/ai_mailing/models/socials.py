import smtplib
from email.mime.text import MIMEText

from odoo import models, fields, api
from dotenv import load_dotenv
import os
import time
from datetime import datetime
import requests
import pywhatkit as kit

load_dotenv()

class SocialEmail(models.Model):
    _name = 'social.email'
    _description = 'Social Email'
    _inherit = ['mail.thread']

    name = fields.Char(string="Email Subject", required=True)
    content = fields.Text(string="Content")
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
    email_addresses = fields.Char(string="Email Addresses", compute="_compute_email_addresses", readonly=True)
    publish_date = fields.Datetime(string="Publish Date")

    @api.depends("recipient_ids")
    def _compute_email_addresses(self):
        for record in self:
            record.email_addresses = ', '.join(record.recipient_ids.mapped('email'))

    def action_confirm(self):
        """Mark message as scheduled"""
        self.write({'mail_scheduling_status': 'scheduled'})
        self.message_post(body=f"WhatsApp message scheduled for {self.publish_date}")

    @api.model
    def cron_send_scheduled_emails(self):
        """Cron job to send scheduled WhatsApp messages."""
        now = datetime.now()
        emails = self.search([
            ('mail_scheduling_status', '=', 'scheduled'),
            ('publish_date', '<=', now)
        ])
        for email in emails:
            email.send_email()

    def send_email(self):
        for record in self:
            sender_email="oussamadarouay@gmail.com"
            password=os.getenv("PASSWORD")

            # Create email message
            msg =MIMEText(self.content)
            msg["Subject"] = self.name
            msg["From"] = sender_email
            msg["To"] = self.email_addresses  # Convert list to comma-separated string

            emails=record.email_addresses = record.email_addresses.split(', ') if record.email_addresses else []


            # SMTP setup and send email
            try:
                server = smtplib.SMTP("smtp.gmail.com", 587)
                server.starttls()  # Secure the connection
                server.login(sender_email, password)
                server.sendmail(sender_email,emails, msg.as_string())  # Send to multiple recipients
                server.quit()
                self.write({'mail_scheduling_status': 'sent'})
                self.message_post(body="Email message successfully sent!")
            except Exception as e:
                self.write({'mail_scheduling_status': 'failed'})
                self.message_post(body=f"Failed to send Email message: {str(e)}")

    def action_cancel(self):
        """Cancel a scheduled WhatsApp message"""
        self.write({'mail_scheduling_status': 'draft'})

class SocialWhatsApp(models.Model):
    _name = 'social.whatsapp'
    _description = 'Social WhatsApp Message'
    _inherit = ['mail.thread']

    name = fields.Char(string="Message Title", required=True)
    message = fields.Text(string="Message")
    is_published = fields.Boolean(string="Is Published", default=False)
    campaign_id = fields.Many2one('marketing.campaign', string='Campaign')
    recipient_ids = fields.Many2many(
        'res.partner',
        string="Recipients",
        domain="[('phone', '!=', False)]"
    )
    phone_numbers = fields.Char(string="Phone Numbers", compute="_compute_phone_numbers", readonly=True)
    publish_date = fields.Datetime(string="Publish Date")
    wa_scheduling_status = fields.Selection([
        ('draft', 'Draft'),
        ('scheduled', 'Scheduled for Sending'),
        ('sent', 'Sent'),
        ('failed', 'Sending Failed')
    ], string="Scheduling Status", default='draft')
    @api.depends("recipient_ids")
    def _compute_phone_numbers(self):
        for record in self:
            record.phone_numbers = ', '.join(record.recipient_ids.mapped('phone'))

    def action_confirm(self):
        """Mark message as scheduled"""
        # self.write({'wa_scheduling_status': 'scheduled'})
        # self.message_post(body=f"WhatsApp message scheduled for {self.publish_date}")
        self.send_whatsapp_message()

    @api.model
    def cron_send_scheduled_messages(self):
        """Cron job to send scheduled WhatsApp messages."""
        now = datetime.now()
        print(now)
        messages = self.search([
            ('wa_scheduling_status', '=', 'scheduled'),
            ('publish_date', '<=', now)
        ])
        for message in messages:
            message.send_whatsapp_message()

    def send_whatsapp_message(self):
        """Send WhatsApp messages using pywhatkit"""
        try:
            a=0
            for recipient in self.recipient_ids:
                phone = recipient.phone
                if not phone:
                    continue  # Skip if no phone number

                text = self.message.strip()
                send_time = self.publish_date
                hours, minutes = int(send_time.hour), int(send_time.minute)
                print(hours, minutes)
                print("Sending Message...")
                minutes=minutes+a
                a=a+1
                # Send message using pywhatkit

                kit.sendwhatmsg(phone, text, hours, (minutes+2), 10, True ,1)
                time.sleep(5)  # Add delay to avoid spam detection

            self.write({'wa_scheduling_status': 'sent'})
            self.message_post(body="WhatsApp message successfully sent!")
        except Exception as e:
            self.write({'wa_scheduling_status': 'failed'})
            self.message_post(body=f"Failed to send WhatsApp message: {str(e)}")

    def action_cancel(self):
        """Cancel a scheduled WhatsApp message"""
        self.write({'wa_scheduling_status': 'draft'})


class SocialInstagram(models.Model):
    _name = "social.instagram"
    _description = "Instagram Posts"
    _inherit = ['mail.thread']

    name = fields.Char(string="Title")
    campaign_id = fields.Many2one('marketing.campaign', string='Campaign')
    image = fields.Char(string="Image url")
    is_published = fields.Boolean(string="Is Published", default=False)
    caption = fields.Text(string="Caption")
    publish_date = fields.Datetime(string="Publish Date")

    #id for the post
    scheduled_ig_post_id = fields.Char(string="Instagram Post ID", help="ID of the scheduled post on Instagram")
    ig_scheduling_status = fields.Selection([
        ('draft', 'Draft'),
        ('scheduled', 'Scheduled on Instagram'),
        ('published', 'Published'),
        ('failed', 'Scheduling Failed')
    ], string="Scheduling Status", default='draft')


    def action_confirm(self):
        """Mark post as scheduled to be processed by cron"""
        self.write({'ig_scheduling_status': 'scheduled'})
        self.message_post(body=f"Instagram post scheduled for {self.publish_date}")

    @api.model
    def cron_publish_scheduled_posts(self):

        now = datetime.utcnow()
        posts = self.search([
            ('ig_scheduling_status', '=', 'scheduled'),
            ('publish_date', '<=', now) # Find posts where the publish date is in the past or now t3ada wala laa
        ])
        for post in posts:
            post.schedule_instagram_post() #after filtering all the posts that needs to be posted nhabtohom taw

    def schedule_instagram_post(self):
        """Create Instagram post and publish"""
        print("Instagram post scheduled")
        try:
            if self.scheduled_ig_post_id:
                return  # Already processed

            graph_api_url = f"https://graph.facebook.com/v22.0/{os.getenv('INSTA_ID')}/media"
            image_url = "https://raw.githubusercontent.com/oarouay/oarouay.github.io/main/oussama.png"
            payload = {
                'caption': f"{self.name}\n\n{self.caption}",
                'image_url': image_url,
                'access_token': os.getenv("IG_ACCESS_TOKEN")
            }
            response = requests.post(graph_api_url, data=payload)
            response_data = response.json()

            if "id" not in response_data:
                raise Exception(response_data.get('error', {}).get('message', 'Unknown error'))

            container_id = response_data["id"]
            publish_url = f"https://graph.facebook.com/v22.0/{os.getenv('INSTA_ID')}/media_publish"
            publish_payload = {
                'creation_id': container_id,
                'access_token': os.getenv("IG_ACCESS_TOKEN")
            }
            publish_response = requests.post(publish_url, data=publish_payload)
            publish_data = publish_response.json()
            print(publish_data)


            if "id" in publish_data:
                self.write({'scheduled_ig_post_id': publish_data['id'], 'ig_scheduling_status': 'published'})
                self.message_post(body="Instagram post successfully published!")
            else:
                raise Exception(publish_data.get('error', {}).get('message', 'Unknown error'))

        except Exception as e:
            self.write({'ig_scheduling_status': 'failed'})
            self.message_post(body=f"Failed to publish Instagram post: {str(e)}")

    def action_cancel(self):
        for record in self:
            record.write({'ig_scheduling_status': 'draft'})

class SocialFacebook(models.Model):
    _name = "social.facebook"
    _description = "Facebook Posts"
    _inherit = ["mail.thread"]

    name = fields.Char(string="Title")
    campaign_id = fields.Many2one('marketing.campaign', string='Campaign')
    content = fields.Text(string="Content")
    publish_date = fields.Datetime(string="Publish Date")
    is_published = fields.Boolean(string="Is Published", default=False)
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

    @api.model
    def crone_check_post_status(self):
        posts = self.search([
            ('fb_scheduling_status', '=', 'scheduled'),
        ])
        for record in posts:
            url = f"https://graph.facebook.com/v17.0/{record.scheduled_fb_post_id}"
            params = {
                'fields': 'id,is_published,status_type',
                'access_token': os.getenv("ACCESS_TOKEN")}
            response = requests.get(url, params=params)
            data = response.json()
            print(data)
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