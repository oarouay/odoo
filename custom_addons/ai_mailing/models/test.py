class SocialMedia(models.Model):
    """Base model for all social media posts"""
    _name = "social.media"
    _description = "Social Media Posts Base"
    _inherit = ['mail.thread']

    name = fields.Char(string="Title")
    campaign_id = fields.Many2one('marketing.campaign', string='Campaign')
    is_published = fields.Boolean(string="Is Published", default=False)
    publish_date = fields.Datetime(string="Publish Date")
    image_ids = fields.Many2many('image.model', string='Images')

    # Common status field with consistent naming
    scheduling_status = fields.Selection([
        ('draft', 'Draft'),
        ('scheduled', 'Scheduled'),
        ('published', 'Published'),
        ('failed', 'Scheduling Failed')
    ], string="Scheduling Status", default='draft')

    def action_view_content(self):
        """Open the form view for this social media post."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('View Post'),
            'res_model': self._name,
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'current',
        }

    def action_confirm(self):
        """Mark post as scheduled to be processed by cron"""
        self.write({'scheduling_status': 'scheduled'})
        platform_name = self._description.split()[0]  # Extract platform name from description
        self.message_post(body=f"{platform_name} post scheduled for {self.publish_date}")

    def action_cancel(self):
        """Reset post status to draft"""
        for record in self:
            record.write({'scheduling_status': 'draft'})

    def schedule_post(self):
        """Abstract method to be implemented by subclasses"""
        raise NotImplementedError("Subclasses must implement schedule_post method")

    @api.model
    def cron_publish_scheduled_posts(self):
        """Generic cron job to publish scheduled posts"""
        now = datetime.utcnow()
        posts = self.search([
            ('scheduling_status', '=', 'scheduled'),
            ('publish_date', '<=', now)
        ])
        for post in posts:
            post.schedule_post()


class SocialX(models.Model):
    _name = "social.x"
    _description = "X (Twitter) Posts"
    _inherit = ['social.media']

    caption = fields.Text(string="Caption")
    scheduled_tweet_id = fields.Char(string="Tweet ID", help="ID of the scheduled tweet on X")

    def action_confirm(self):
        """Mark tweet as scheduled to be processed by cron"""
        self.write({'scheduling_status': 'scheduled'})
        self.message_post(body=f"Tweet scheduled for {self.publish_date}")

    @api.model
    def cron_send_scheduled_x_posts(self):
        """Cron job to publish scheduled tweets"""
        now = datetime.utcnow()
        posts = self.search([
            ('scheduling_status', '=', 'scheduled'),
            ('publish_date', '<=', now)
        ])
        for post in posts:
            post.schedule_post()

    def _post_tweet(self, text, media_ids=None, reply_to_tweet_id=None):
        """Helper method to post a single tweet"""
        config = self.env['ir.config_parameter'].sudo()
        auth = OAuth1(
            config.get_param('CUSTOMER_KEY'),
            config.get_param('CUSTOMER_KEY_SECRET'),
            config.get_param('X_ACCESS_TOKEN'),
            config.get_param('X_ACCESS_TOKEN_SECRET')
        )

        payload = {"text": text}
        if media_ids:
            payload["media"] = {"media_ids": media_ids}
        if reply_to_tweet_id:
            payload["reply"] = {"in_reply_to_tweet_id": reply_to_tweet_id}

        response = requests.post(
            "https://api.twitter.com/2/tweets",
            json=payload,
            headers={"Content-Type": "application/json"},
            auth=auth
        )

        response.raise_for_status()
        return response.json()

    def _upload_media(self, image_url):
        """Upload media to Twitter and return media_id"""
        config = self.env['ir.config_parameter'].sudo()
        auth = OAuth1(
            config.get_param('CUSTOMER_KEY'),
            config.get_param('CUSTOMER_KEY_SECRET'),
            config.get_param('X_ACCESS_TOKEN'),
            config.get_param('X_ACCESS_TOKEN_SECRET')
        )

        try:
            image_content = requests.get(image_url).content
            response = requests.post(
                "https://upload.twitter.com/1.1/media/upload.json",
                files={'media': ('image.jpg', image_content, 'image/jpeg')},
                auth=auth
            )
            response.raise_for_status()
            return response.json().get("media_id_string")
        except Exception as e:
            print(f"Failed to upload media: {str(e)}")
            raise UserError(_("Failed to upload image: %s") % str(e))

    def schedule_post(self):
        """Create and publish a tweet thread if content exceeds 280 chars"""
        try:
            if self.scheduled_tweet_id:
                return  # Already processed

            # Prepare base text (name + caption)
            base_text = f"{self.name}\n\n" if self.name else ""
            full_text = base_text + (self.caption or "")

            # Upload media if exists (only for first tweet in thread)
            media_ids = []
            if self.image_ids:
                for image in self.image_ids:
                    media_id = self._upload_media(image.url)
                    if media_id:
                        media_ids.append(media_id)

            # Split text into tweet-sized chunks
            chunks = []
            current_chunk = ""

            # Split by paragraphs if possible
            paragraphs = full_text.split('\n')
            for para in paragraphs:
                if len(current_chunk) + len(para) + 1 < 280:  # +1 for newline
                    current_chunk += para + '\n'
                else:
                    if current_chunk:
                        chunks.append(current_chunk.strip())
                    current_chunk = para + '\n' if len(para) < 280 else para[:280]

            if current_chunk:
                chunks.append(current_chunk.strip())

            # Ensure no chunk exceeds 280 chars (fallback)
            final_chunks = []
            for chunk in chunks:
                while len(chunk) > 280:
                    final_chunks.append(chunk[:280])
                    chunk = chunk[280:]
                final_chunks.append(chunk)

            # Post thread
            previous_tweet_id = None
            for i, chunk in enumerate(final_chunks):
                try:
                    # Only attach media to first tweet
                    current_media = media_ids if i == 0 else None

                    response = self._post_tweet(
                        text=chunk,
                        media_ids=current_media,
                        reply_to_tweet_id=previous_tweet_id
                    )

                    tweet_id = response.get("data", {}).get("id")
                    if tweet_id:
                        previous_tweet_id = tweet_id
                        if i == 0:  # First tweet in thread
                            self.write({
                                'scheduled_tweet_id': tweet_id,
                                'scheduling_status': 'published',
                                'is_published': True
                            })
                            self.message_post(body=_("First tweet in thread published (ID: %s)") % tweet_id)
                        else:
                            self.message_post(body=_("Thread continuation published (ID: %s)") % tweet_id)
                except Exception as e:
                    print(f"Failed to post tweet {i + 1}/{len(final_chunks)}: {str(e)}")
                    raise UserError(_("Failed to post tweet %d/%d: %s") % (i + 1, len(final_chunks), str(e)))

            if not previous_tweet_id:
                raise UserError(_("No tweets were published in the thread"))

        except Exception as e:
            self.write({'scheduling_status': 'failed'})
            self.message_post(body=_("Failed to publish tweet thread: %s") % str(e))
            print("Tweet thread failed: %s", str(e), exc_info=True)
            raise


class SocialInstagram(models.Model):
    _name = "social.instagram"
    _description = "Instagram Posts"
    _inherit = ['social.media']

    caption = fields.Text(string="Caption")
    scheduled_ig_post_id = fields.Char(string="Instagram Post ID", help="ID of the scheduled post on Instagram")

    # Override to make images required for Instagram
    image_ids = fields.Many2many('image.model', string='Images', required=True)

    def schedule_post(self):
        """Create an Instagram post and publish with either a single image or multiple images (carousel post)."""
        print("Instagram post scheduling started")
        config = self.env['ir.config_parameter'].sudo()
        try:
            if self.scheduled_ig_post_id:
                return  # Already processed

            # Ensure there are images in the post
            if not self.image_ids:
                raise Exception("No images provided for the Instagram post.")

            access_token = config.get_param('IG_ACCESS_TOKEN')
            insta_id = config.get_param('INSTA_ID')

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
                    self.write({
                        'scheduled_ig_post_id': publish_data['id'],
                        'scheduling_status': 'published',
                        'is_published': True
                    })
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
                    self.write({
                        'scheduled_ig_post_id': publish_data['id'],
                        'scheduling_status': 'published',
                        'is_published': True
                    })
                    self.message_post(body="Instagram carousel post successfully published!")
                else:
                    raise Exception(publish_data.get('error', {}).get('message', 'Unknown error'))

        except Exception as e:
            self.write({'scheduling_status': 'failed'})
            self.message_post(body=f"Failed to publish Instagram post: {str(e)}")


class SocialFacebook(models.Model):
    _name = "social.facebook"
    _description = "Facebook Posts"
    _inherit = ["social.media"]

    content = fields.Text(string="Content")
    scheduled_fb_post_id = fields.Char(string="Facebook Post ID", help="ID of the scheduled post on Facebook")

    # Override to make images required for Facebook
    image_ids = fields.Many2many('image.model', string='Images', required=True)

    def schedule_post(self):
        """Create Facebook post with multiple images using feed endpoint"""
        config = self.env['ir.config_parameter'].sudo()
        try:
            if self.scheduled_fb_post_id:
                return

            # Ensure there are images in the post
            if not self.image_ids:
                raise Exception("No images provided for the Facebook post.")

            # Prepare message
            full_message = f"{self.name}\n\n{self.content}"

            # For Facebook feed posts with multiple images
            graph_api_url = f"https://graph.facebook.com/v17.0/{config.get_param('PAGE_ID')}/feed"

            if len(self.image_ids) == 1:
                # Single image post
                payload = {
                    'message': full_message,
                    'link': self.image_ids[0].url,  # Link to the image
                    'access_token': config.get_param('ACCESS_TOKEN')
                }
            else:
                # Multiple images - use JSON array of attachments
                attached_media = []
                for image in self.image_ids:
                    # First, upload each photo without publishing
                    upload_url = f"https://graph.facebook.com/v17.0/{config.get_param('PAGE_ID')}/photos"
                    upload_payload = {
                        'url': image.url,
                        'published': False,  # Don't publish immediately
                        'access_token': config.get_param('ACCESS_TOKEN')
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
                    'access_token': config.get_param('ACCESS_TOKEN')
                }

            # Make the post
            response = requests.post(graph_api_url, data=payload)
            response_data = response.json()
            print("Facebook post created: ", response_data)

            if 'id' in response_data:
                self.write({
                    'scheduled_fb_post_id': response_data['id'],
                    'scheduling_status': 'published',
                    'is_published': True
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
            self.write({'scheduling_status': 'failed'})
            self.message_post(body=f"Failed to publish Facebook post: {str(e)}")
            return False