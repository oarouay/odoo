import json
from requests_oauthlib import OAuth1
from odoo import models, fields, api
from dotenv import load_dotenv
import os
from datetime import datetime
import requests
from odoo.exceptions import UserError
load_dotenv()


class SocialEmail(models.Model):
    _name = 'social.email'
    _description = 'Social Email'
    _inherit = ['mail.thread']

    name = fields.Char(string="Email Subject", required=True)
    content = fields.Html(string="Content")
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
    mailing_id = fields.Many2one('mailing.mailing', string='Mass Mailing', ondelete='set null')

    @api.depends("recipient_ids")
    def _compute_email_addresses(self):
        for record in self:
            record.email_addresses = ', '.join(record.recipient_ids.mapped('email'))

    def action_confirm(self):
        """Mark message as scheduled and create mass mailing with personalized content."""
        self.ensure_one()
        # Ensure recipient_ids is a list of IDs
        recipient_ids = self.recipient_ids.ids
        if not recipient_ids:
            raise UserError("No recipients selected for the email.")

        # Create a mailing.mailing record
        personalized_contents = []
        for recipient in self.recipient_ids:
            personalized_content = self.content.replace('{name}', recipient.name)
            personalized_contents.append((personalized_content, recipient.id))

        # Create a mailing.mailing record with the first recipient's content
        for personalized_content in personalized_contents:
            print(personalized_content)
            vals = {
                'subject': self.name,
                'body_html': personalized_content[0] if personalized_content[0] else self.content,
                'mailing_model_id':self.env['ir.model']._get('res.partner').id,
                # Adjust to correct mailing model
                'mailing_domain': [('list_ids', '=', personalized_content[1])],  # Correct the domain filter
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
        record = self.env['mailing.mailing'].browse(self.mailing_id.id)
        record.unlink()
        self.write({'mail_scheduling_status': 'draft'})
        self.message_post(body="Email scheduling cancelled")

class SocialX(models.Model):
    _name = "social.x"
    _description = "X (Twitter) Posts"
    _inherit = ['mail.thread']

    name = fields.Char(string="Title")
    campaign_id = fields.Many2one('marketing.campaign', string='Campaign')
    is_published = fields.Boolean(string="Is Published", default=False)
    caption = fields.Text(string="Caption")
    publish_date = fields.Datetime(string="Publish Date")
    image_ids = fields.Many2many('image.model', string='Images')

    # ID for the tweet
    scheduled_tweet_id = fields.Char(string="Tweet ID", help="ID of the scheduled tweet on X")
    x_scheduling_status = fields.Selection([
        ('draft', 'Draft'),
        ('scheduled', 'Scheduled on X'),
        ('published', 'Published'),
        ('failed', 'Scheduling Failed')
    ], string="Scheduling Status", default='draft')

    def action_confirm(self):
        """Mark tweet as scheduled to be processed by cron"""
        self.write({'x_scheduling_status': 'scheduled'})
        self.message_post(body=f"Tweet scheduled for {self.publish_date}")

    @api.model
    def cron_send_scheduled_x_posts(self):
        """Cron job to publish scheduled tweets"""
        now = datetime.utcnow()
        print(now)
        posts = self.search([
            ('x_scheduling_status', '=', 'scheduled'),
            ('publish_date', '<=', now)  # Fetch posts that are due for publishing
        ])
        for post in posts:
            post.schedule_tweet()  # Publish each post

    def schedule_tweet(self):
        """Create and publish a tweet with or without images"""
        try:
            if self.scheduled_tweet_id:
                return  # Already processed

            tweet_text = f"{self.name}\n\n{self.caption}"

            # OAuth 1.0a Authentication
            auth = OAuth1(
                os.getenv("CUSTOMER_KEY"),
                os.getenv("CUSTOMER_KEY_SECRET"),
                os.getenv("X_ACCESS_TOKEN"),
                os.getenv("X_ACCESS_TOKEN_SECRET")
            )

            headers = {"Content-Type": "application/json"}
            media_ids = []

            if self.image_ids:
                for image in self.image_ids:
                    try:
                        image_content = requests.get(image.url).content
                        media_url = "https://upload.twitter.com/1.1/media/upload.json"
                        files = {'media': ('image.jpg', image_content, 'image/jpeg')}
                        media_response = requests.post(media_url, files=files, auth=auth)
                        media_data = media_response.json()

                        if "media_id_string" in media_data:
                            media_ids.append(media_data["media_id_string"])
                        else:
                            self.message_post(body=f"Warning: Failed to upload image: {media_data}")
                    except Exception as img_err:
                        self.message_post(body=f"Error uploading image: {str(img_err)}")

            # Prepare payload
            payload = {"text": tweet_text}
            if media_ids:
                payload["media"] = {"media_ids": media_ids}

            api_url = "https://api.twitter.com/2/tweets"
            response = requests.post(api_url, json=payload, headers=headers, auth=auth)
            response_data = response.json()

            if "data" in response_data and "id" in response_data["data"]:
                self.write({'scheduled_tweet_id': response_data["data"]["id"], 'x_scheduling_status': 'published'})
                self.message_post(body=f"Tweet{' with images' if media_ids else ''} successfully published!")
            else:
                raise Exception(response_data.get('errors', [{}])[0].get('message', 'Unknown error'))

        except Exception as e:
            self.write({'x_scheduling_status': 'failed'})
            self.message_post(body=f"Failed to publish tweet: {str(e)}")

    def action_cancel(self):
        """Reset tweet status to draft"""
        for record in self:
            record.write({'x_scheduling_status': 'draft'})

class SocialInstagram(models.Model):
    _name = "social.instagram"
    _description = "Instagram Posts"
    _inherit = ['mail.thread']

    name = fields.Char(string="Title")
    campaign_id = fields.Many2one('marketing.campaign', string='Campaign')
    is_published = fields.Boolean(string="Is Published", default=False)
    caption = fields.Text(string="Caption")
    publish_date = fields.Datetime(string="Publish Date")
    image_ids = fields.Many2many('image.model', string='Images',required=True)
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
        """Create an Instagram post and publish with either a single image or multiple images (carousel post)."""
        print("Instagram post scheduling started")
        try:
            if self.scheduled_ig_post_id:
                return  # Already processed

            # Ensure there are images in the post
            if not self.image_ids:
                raise Exception("No images provided for the Instagram post.")

            access_token = os.getenv("IG_ACCESS_TOKEN")
            insta_id = os.getenv("INSTA_ID")

            if len(self.image_ids) == 1:
                # Single image post
                image_url = self.image_ids[0].url
                graph_api_url = f"https://graph.facebook.com/v22.0/{insta_id}/media"
                payload = {
                    'image_url': image_url,
                    'caption': f"{self.name}\n\n{self.caption}",
                    'access_token': access_token
                }

                response = requests.post(graph_api_url, data=payload)
                response_data = response.json()
                print("Single image uploaded: ", response_data)

                if "id" not in response_data:
                    raise Exception(
                        f"Error uploading image: {response_data.get('error', {}).get('message', 'Unknown error')}")

                # Publish the single image
                publish_url = f"https://graph.facebook.com/v22.0/{insta_id}/media_publish"
                publish_payload = {
                    'creation_id': response_data['id'],
                    'access_token': access_token
                }

                publish_response = requests.post(publish_url, data=publish_payload)
                publish_data = publish_response.json()
                print("Single image published: ", publish_data)

                if "id" in publish_data:
                    self.write({'scheduled_ig_post_id': publish_data['id'], 'ig_scheduling_status': 'published'})
                    self.message_post(body="Instagram single image post successfully published!")
                else:
                    raise Exception(publish_data.get('error', {}).get('message', 'Unknown error'))

            else:
                # Carousel post
                media_ids = []
                for image in self.image_ids:
                    image_url = image.url
                    graph_api_url = f"https://graph.facebook.com/v22.0/{insta_id}/media"
                    payload = {
                        'media_type': 'IMAGE',
                        'image_url': image_url,
                        'is_carousel_item': 'true',
                        'access_token': access_token
                    }

                    response = requests.post(graph_api_url, data=payload)
                    response_data = response.json()
                    print("Images uploaded: ", response_data)

                    if "id" not in response_data:
                        raise Exception(
                            f"Error uploading image: {response_data.get('error', {}).get('message', 'Unknown error')}")

                    media_ids.append(response_data["id"])

                # Create a media container (carousel)
                container_url = f"https://graph.facebook.com/v22.0/{insta_id}/media"
                container_payload = {
                    'media_type': 'CAROUSEL',
                    'caption': f"{self.name}\n\n{self.caption}",
                    'children': ",".join(media_ids),
                    'access_token': access_token
                }

                container_response = requests.post(container_url, data=container_payload)
                container_data = container_response.json()
                print("Carousel container created: ", container_data)

                if "id" not in container_data:
                    raise Exception(
                        f"Error creating media container: {container_data.get('error', {}).get('message', 'Unknown error')}")

                # Publish the carousel post
                publish_url = f"https://graph.facebook.com/v22.0/{insta_id}/media_publish"
                publish_payload = {
                    'creation_id': container_data['id'],
                    'access_token': access_token
                }

                publish_response = requests.post(publish_url, data=publish_payload)
                publish_data = publish_response.json()
                print("Carousel published: ", publish_data)

                if "id" in publish_data:
                    self.write({'scheduled_ig_post_id': publish_data['id'], 'ig_scheduling_status': 'published'})
                    self.message_post(body="Instagram carousel post successfully published!")
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
    image_ids = fields.Many2many('image.model', string='Images', required=True)
    scheduled_fb_post_id = fields.Char(string="Facebook Post ID", help="ID of the scheduled post on Facebook")
    fb_scheduling_status = fields.Selection([
        ('draft', 'Draft'),
        ('scheduled', 'Scheduled on Facebook'),
        ('published', 'Published'),
        ('failed', 'Scheduling Failed')
    ], string="Scheduling Status", default='draft')

    def action_confirm(self):
        """Mark post as scheduled to be processed by cron"""
        self.write({'fb_scheduling_status': 'scheduled'})
        self.message_post(body=f"Facebook post scheduled for {self.publish_date}")

    @api.model
    def cron_publish_scheduled_posts(self):
        """Cron job to publish posts that are due"""
        now = datetime.utcnow()
        posts = self.search([
            ('fb_scheduling_status', '=', 'scheduled'),
            ('publish_date', '<=', now)  # Find posts where the publish date is in the past or now
        ])
        for post in posts:
            post.schedule_facebook_post()

    def schedule_facebook_post(self):
        """Create Facebook post with multiple images using feed endpoint"""
        try:
            if self.scheduled_fb_post_id:
                return  # Already processed

            # Ensure there are images in the post
            if not self.image_ids:
                raise Exception("No images provided for the Facebook post.")

            # Prepare message
            full_message = f"{self.name}\n\n{self.content}"

            # For Facebook feed posts with multiple images
            graph_api_url = f"https://graph.facebook.com/v17.0/{os.getenv('PAGE_ID')}/feed"

            if len(self.image_ids) == 1:
                # Single image post
                payload = {
                    'message': full_message,
                    'link': self.image_ids[0].url,  # Link to the image
                    'access_token': os.getenv("ACCESS_TOKEN")
                }
            else:
                # Multiple images - use JSON array of attachments
                attached_media = []
                for image in self.image_ids:
                    # First, upload each photo without publishing
                    upload_url = f"https://graph.facebook.com/v17.0/{os.getenv('PAGE_ID')}/photos"
                    upload_payload = {
                        'url': image.url,
                        'published': False,  # Don't publish immediately
                        'access_token': os.getenv("ACCESS_TOKEN")
                    }

                    upload_response = requests.post(upload_url, data=upload_payload)
                    upload_data = upload_response.json()

                    if 'id' in upload_data:
                        attached_media.append({'media_fbid': upload_data['id']})
                    else:
                        error_message = upload_data.get('error', {}).get('message', 'Unknown error')
                        self.message_post(body=f"Warning: Failed to upload image: {error_message}")
                        continue

                if not attached_media:
                    raise Exception("Failed to upload any images")

                # Now create a post with all the attached media
                payload = {
                    'message': full_message,
                    'attached_media': json.dumps(attached_media),
                    'access_token': os.getenv("ACCESS_TOKEN")
                }

            # Make the post
            response = requests.post(graph_api_url, data=payload)
            response_data = response.json()

            if 'id' in response_data:
                self.write({
                    'scheduled_fb_post_id': response_data['id'],
                    'fb_scheduling_status': 'published'
                })
                if len(self.image_ids) == 1:
                    self.message_post(body="Facebook post with image successfully published!")
                else:
                    self.message_post(body=f"Facebook post with {len(attached_media)} images successfully published!")
                return True
            else:
                error_message = response_data.get('error', {}).get('message', 'Unknown error')
                raise Exception(error_message)

        except Exception as e:
            self.write({'fb_scheduling_status': 'failed'})
            self.message_post(body=f"Failed to publish Facebook post: {str(e)}")
            return False

    def action_cancel(self):
        for record in self:
            record.write({'scheduled_fb_post_id': 'draft'})