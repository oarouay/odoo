import base64
import git
from pathlib import Path
from odoo import models, fields, api


class ImageModel(models.Model):
    _name = 'image.model'
    _description = 'Model for storing an image with its name and description'

    name = fields.Char(string='Image Name', required=True)
    description = fields.Text(string='Description')
    url = fields.Char(string='URL')
    urldes = fields.Char(string="AI Prompt", compute='_compute_ai_prompt', store=True)


    @api.depends('url', 'description', 'name')
    def _compute_ai_prompt(self):
        for record in self:
            if record.url and record.description:
                record.urldes = f"Image Name: {record.name}, URL: {record.url}, Description: {record.description}."
            else:
                record.urldes = ''

class ProductImageDownloader:
    def __init__(self, env):
        """
        Initialize the Product Image Downloader
        """
        self.env = env
        self.repo_path = Path("/opt/odoo/product_images")  # Adjust if needed
        self.repo_url = "https://github.com/oarouay/product_images.git"
        self.branch = "master"  # Changed from 'main' to 'master' based on your logs

        # Ensure local repository exists
        if not self.repo_path.exists():
            self.repo_path.mkdir(parents=True, exist_ok=True)
            try:
                print(f"Cloning repository from {self.repo_url}...")
                self.repo = git.Repo.clone_from(self.repo_url, self.repo_path)
                print("Repository cloned successfully")
            except git.exc.GitCommandError as e:
                print(f"ERROR during git clone: {e}")
                raise
        else:
            print(f"Repository directory exists at {self.repo_path}")

        try:
            self.repo = git.Repo(self.repo_path)

            # Verify remote configuration
            try:
                origin = self.repo.remote(name='origin')
                print(f"Remote 'origin' URL: {origin.url}")
            except ValueError:
                print("Remote 'origin' not found, adding it...")
                self.repo.create_remote('origin', self.repo_url)

            # Check if remote exists and initialize if needed
            try:
                # List remote branches
                remote_refs = self.repo.git.ls_remote('--heads', 'origin').split('\n')
                print(f"Remote branches: {remote_refs}")

                # If repo is empty, initialize with current branch
                if not remote_refs or remote_refs[0] == '':
                    print("Remote repository appears to be empty, initializing it")

                    # Make sure we have a README
                    readme_path = self.repo_path / 'README.md'
                    if not readme_path.exists():
                        with open(readme_path, 'w') as f:
                            f.write('# Product Images\nThis repository contains product images uploaded from Odoo.')
                        self.repo.git.add(str(readme_path))

                    # Create images directory
                    image_dir = self.repo_path / 'product_images'
                    image_dir.mkdir(parents=True, exist_ok=True)

                    # Configure git user
                    try:
                        self.repo.git.config('user.email', 'odoo@example.com')
                        self.repo.git.config('user.name', 'Odoo System')
                    except Exception as e:
                        print(f"Warning: Could not set git user config: {e}")

                    # Initial commit if needed
                    if self.repo.is_dirty() or self.repo.untracked_files:
                        self.repo.git.add(A=True)
                        self.repo.git.commit('-m', 'Initial repository setup')

                    # Push initial commit to initialize the repository
                    try:
                        print(f"Pushing initial commit to branch {self.branch}")
                        origin = self.repo.remote(name='origin')
                        origin.push(self.branch)
                        print("Initial push successful!")
                    except git.exc.GitCommandError as e:
                        print(f"Initial push error: {e}")
                        # Try force push for initial setup
                        try:
                            print("Trying force push for initial setup...")
                            origin.push('--force', self.branch)
                            print("Force push successful!")
                        except Exception as force_e:
                            print(f"Force push failed: {force_e}")
            except git.exc.GitCommandError as e:
                print(f"Error checking remote branches: {e}")

            # Make sure we're on the correct branch
            try:
                current_branch = self.repo.active_branch.name
                print(f"Current branch: {current_branch}")
                if current_branch != self.branch:
                    try:
                        print(f"Switching to branch {self.branch}")
                        self.repo.git.checkout(self.branch)
                    except git.exc.GitCommandError:
                        print(f"Branch {self.branch} doesn't exist locally, creating it")
                        self.repo.git.checkout('-b', self.branch)
            except Exception as e:
                print(f"Branch handling error: {e}")

            # Try to pull latest changes
            try:
                print("Pulling latest changes...")
                self.repo.git.pull('origin', self.branch)
            except git.exc.GitCommandError as e:
                print(f"Pull error (non-fatal): {e}")

        except git.exc.InvalidGitRepositoryError:
            print(f"Invalid git repository at {self.repo_path}, initializing new one")
            self.repo = git.Repo.init(self.repo_path)
            self.repo.create_remote('origin', self.repo_url)

            # Create initial structure
            readme_path = self.repo_path / 'README.md'
            with open(readme_path, 'w') as f:
                f.write('# Product Images\nThis repository contains product images uploaded from Odoo.')

            image_dir = self.repo_path / 'product_images'
            image_dir.mkdir(parents=True, exist_ok=True)

            self.repo.git.add(A=True)

            # Configure git user
            try:
                self.repo.git.config('user.email', 'odoo@example.com')
                self.repo.git.config('user.name', 'Odoo System')
            except:
                print("Warning: Could not set git user config")

            self.repo.git.commit('-m', 'Initial commit')

        print("Is repo dirty?", self.repo.is_dirty())  # Check if there are uncommitted changes
        print("Untracked files:", self.repo.untracked_files)  # Check for new files
        try:
            print("Last commit:", self.repo.head.commit.message)  # Last commit message
        except:
            print("No commits yet")

    def download_product_images(self):
        """
        Download images for products and push to GitHub
        """
        # First, fetch existing images from image.model to avoid duplicates
        existing_images = {}
        for record in self.env['image.model'].search([]):
            if record.description and record.description.isdigit():
                existing_images[int(record.description)] = record.url

        print(f"Found {len(existing_images)} existing image records")

        # Search for products with images
        products = self.env['product.product'].search([])
        products_with_images = [p for p in products if p.image_1920]
        print(f"Found {len(products_with_images)} products with images")

        image_dir = self.repo_path / 'product_images'
        image_dir.mkdir(parents=True, exist_ok=True)

        created_images = []
        files_added = False

        # Check if directory exists in repository
        product_images_dir_exists = (self.repo_path / 'product_images').exists()
        if not product_images_dir_exists:
            print("Creating product_images directory")
            image_dir.mkdir(parents=True, exist_ok=True)
            # Add the directory to git
            placeholder_file = image_dir / '.gitkeep'
            with open(placeholder_file, 'w') as f:
                f.write('')
            self.repo.git.add(str(placeholder_file))
            files_added = True

        for product in products_with_images:
            if not product.image_1920:
                print(f"Skipping product {product.id}: No valid image found")
                continue

            # Skip if we already have this image
            if product.id in existing_images:
                print(f"Image for product {product.id} already exists in database, skipping")
                continue

            safe_filename = f"{product.id}.png"
            file_path = image_dir / safe_filename

            # Skip if file already exists physically
            if file_path.exists():
                # If file exists but we don't have a DB record, create one
                if product.id not in existing_images:
                    print(f"File exists for product {product.id} but no DB record, creating record")
                    base_url = f"https://raw.githubusercontent.com/oarouay/product_images/{self.branch}/product_images/"
                    image_url = f"{base_url}{safe_filename}"

                    image_record = self.env['image.model'].create({
                        'name': product.description_sale or product.name,
                        'description': str(product.id),
                        'url': image_url
                    })
                    created_images.append(image_record)
                continue

            try:
                print(f"Processing image for product {product.id}")

                # Ensure image_1920 is base64 encoded
                if not isinstance(product.image_1920, (str, bytes)):
                    print(f"Invalid image data type for product {product.id}")
                    continue

                try:
                    image_data = base64.b64decode(product.image_1920)
                except Exception as decode_error:
                    print(f"Could not decode image for product {product.id}: {decode_error}")
                    continue

                with open(file_path, 'wb') as f:
                    f.write(image_data)

                # Make sure the file was created successfully
                if not file_path.exists() or file_path.stat().st_size == 0:
                    print(f"Failed to write image file for product {product.id}")
                    continue

                self.repo.git.add(str(file_path))
                files_added = True
                print(f"Added file {file_path} to git staging")

                base_url = f"https://raw.githubusercontent.com/oarouay/product_images/{self.branch}/product_images/"
                image_url = f"{base_url}{safe_filename}"

                image_record = self.env['image.model'].create({
                    'name': product.description_sale or product.name,
                    'description': str(product.id),
                    'url': image_url
                })
                print(f"Created image record for product {product.id}")

                created_images.append(image_record)

            except Exception as e:
                print(f"Error processing image for product {product.id}: {e}")
                import traceback
                traceback.print_exc()

        # Configure git user if needed
        try:
            print("Setting git user config...")
            email = self.repo.git.config('user.email')
            name = self.repo.git.config('user.name')
            print(f"Current git user: {name} <{email}>")
        except:
            print("Setting git user defaults")
            self.repo.git.config('user.email', 'odoo@example.com')
            self.repo.git.config('user.name', 'Odoo System')

        # Verify if we have changes to commit
        print("Checking for changes to commit...")
        status_output = self.repo.git.status()
        print(f"Git status: {status_output}")

        # Only try to commit if we have changes
        if "nothing to commit" not in status_output or files_added:
            try:
                print("Committing changes...")
                self.repo.git.add('--all')  # Add all changes, including untracked files

                # Check status again after adding
                status_after_add = self.repo.git.status()
                print(f"Git status after add: {status_after_add}")

                if "nothing to commit" not in status_after_add:
                    self.repo.git.commit('-m', 'Update product images')
                    print("Changes committed successfully")

                    print(f"Pushing to GitHub branch {self.branch}...")
                    origin = self.repo.remote(name='origin')
                    try:
                        push_result = origin.push(self.branch)
                        print(f"Push result: {push_result}")
                        print("✅ Images pushed successfully!")
                    except git.exc.GitCommandError as e:
                        print(f"🚨 Push error: {e}")
                        if "rejected" in str(e):
                            print("Attempting to resolve by pulling first...")
                            try:
                                self.repo.git.pull('--rebase', 'origin', self.branch)
                                origin.push(self.branch)
                                print("✅ Pull and push successful!")
                            except git.exc.GitCommandError as e2:
                                print(f"🚨 Pull and push failed: {e2}")
                                print("Attempting force push as last resort...")
                                try:
                                    origin.push('--force', self.branch)
                                    print("✅ Force push successful!")
                                except Exception as e3:
                                    print(f"🚨 Force push failed: {e3}")
                                    print("❗ GitHub push completely failed, please check credentials and permissions")
                else:
                    print("No changes to commit after git add")
            except Exception as e:
                print(f"🚨 Error during commit/push: {e}")
                import traceback
                traceback.print_exc()
        else:
            print("ℹ️ No changes to commit. Repository is clean.")

        return created_images


class ImageCronJob(models.Model):
    _inherit = 'image.model'

    @api.model
    def cron_upload_product_images(self):
        """
        Scheduled Cron Job to Upload New Product Images to GitHub
        """
        image_downloader = ProductImageDownloader(self.env)
        image_downloader.download_product_images()


class LinkModel(models.Model):
    _name = 'link.model'
    _description = 'Model for storing a link with its name and description'

    name = fields.Char(string='Link Name', required=True)
    description = fields.Text(string='Description')
    url = fields.Char(string='URL', required=True)
    urldes = fields.Char(string="Formatted Description", compute='_compute_formatted_description', store=True)

    @api.depends('url', 'description')
    def _compute_formatted_description(self):
        for record in self:
            # Concatenate the link URL and description, separated by a comma
            record.urldes = f"The link URL: {record.url}, Description: {record.description}." if record.url and record.description else record.url or record.description or ''
