"""
Tests for user profile image upload and retrieval functionality
"""

import os
import tempfile
from io import BytesIO
from unittest.mock import mock_open, patch, call

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.authentication.models import Company

User = get_user_model()


class TestUserImageView(APITestCase):
    """Test UserImageView for profile image upload and retrieval"""

    def setUp(self):
        """Set up test data"""
        self.company = Company.objects.create(name="Test Company", domain="@testcompany.com")

        # Create regular user
        self.user = User.objects.create_user(
            email="testuser@testcompany.com",
            password="testpass123",
            first_name="Test",
            last_name="User",
            company=self.company,
            role="developer",
        )

        # Create admin user
        self.admin_user = User.objects.create_user(
            email="admin@testcompany.com",
            password="adminpass123",
            first_name="Admin",
            last_name="User",
            company=self.company,
            role="admin",
        )

        # Create user from different company
        self.other_company = Company.objects.create(name="Other Company", domain="@othercompany.com")
        self.other_user = User.objects.create_user(
            email="other@othercompany.com",
            password="otherpass123",
            first_name="Other",
            last_name="User",
            company=self.other_company,
            role="developer",
        )

    def create_test_image_data(self, format="PNG", size_kb=10):
        """Create fake image data for testing"""
        # Create some fake image data
        data_size = size_kb * 1024
        return (
            b"\x89PNG\r\n\x1a\n" + b"\x00" * (data_size - 8)
            if format == "PNG"
            else b"\xff\xd8\xff\xe0" + b"\x00" * (data_size - 4)
        )

    def create_upload_file(self, filename="test.png", format="PNG", size_kb=10):
        """Create SimpleUploadedFile for testing"""
        image_data = self.create_test_image_data(format=format, size_kb=size_kb)
        return SimpleUploadedFile(filename, image_data, content_type=f"image/{format.lower()}")

    @patch("os.path.exists")
    @patch("os.makedirs")
    @patch("builtins.open", new_callable=mock_open)
    def test_upload_image_success(self, mock_file, mock_makedirs, mock_exists):
        """Test successful image upload"""
        mock_exists.return_value = True

        self.client.force_authenticate(user=self.user)
        url = reverse("user_image", kwargs={"user_id": self.user.id})

        image_file = self.create_upload_file()

        response = self.client.post(url, {"image": image_file}, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("message", response.data)
        self.assertIn("profile_image_path", response.data)
        self.assertEqual(response.data["message"], "Profile image uploaded successfully")

        # Verify user's profile_image_path was updated
        self.user.refresh_from_db()
        self.assertTrue(self.user.profile_image_path.startswith(str(self.user.id)))
        self.assertTrue(self.user.profile_image_path.endswith("test.png"))

    def test_upload_image_no_authentication(self):
        """Test image upload without authentication"""
        url = reverse("user_image", kwargs={"user_id": self.user.id})
        image_file = self.create_upload_file()

        response = self.client.post(url, {"image": image_file}, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_upload_image_access_denied(self):
        """Test image upload for another user without admin privileges"""
        self.client.force_authenticate(user=self.user)
        url = reverse("user_image", kwargs={"user_id": self.other_user.id})

        image_file = self.create_upload_file()

        response = self.client.post(url, {"image": image_file}, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("error", response.data)

    @patch("os.path.exists")
    @patch("os.makedirs")
    @patch("builtins.open", new_callable=mock_open)
    def test_admin_upload_image_for_other_user(self, mock_file, mock_makedirs, mock_exists):
        """Test admin can upload image for another user"""
        mock_exists.return_value = True

        self.client.force_authenticate(user=self.admin_user)
        url = reverse("user_image", kwargs={"user_id": self.user.id})

        image_file = self.create_upload_file()

        response = self.client.post(url, {"image": image_file}, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("profile_image_path", response.data)

    def test_upload_image_no_file(self):
        """Test image upload without providing file"""
        self.client.force_authenticate(user=self.user)
        url = reverse("user_image", kwargs={"user_id": self.user.id})

        response = self.client.post(url, {}, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)
        self.assertEqual(response.data["error"], "No image file provided")

    def test_upload_image_invalid_file_type(self):
        """Test image upload with invalid file type"""
        self.client.force_authenticate(user=self.user)
        url = reverse("user_image", kwargs={"user_id": self.user.id})

        # Create a text file instead of image
        text_file = SimpleUploadedFile("test.txt", b"This is a text file", content_type="text/plain")

        response = self.client.post(url, {"image": text_file}, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)
        self.assertEqual(response.data["error"], "Only PNG and JPEG images are allowed")

    def test_upload_image_file_too_large(self):
        """Test image upload with file size exceeding limit"""
        self.client.force_authenticate(user=self.user)
        url = reverse("user_image", kwargs={"user_id": self.user.id})

        # Create a large image file (6MB)
        large_file = self.create_upload_file("large.png", format="PNG", size_kb=6144)

        response = self.client.post(url, {"image": large_file}, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)
        self.assertEqual(response.data["error"], "Image file too large. Maximum size is 5MB")

    def test_upload_image_user_not_found(self):
        """Test image upload for non-existent user"""
        self.client.force_authenticate(user=self.admin_user)
        url = reverse("user_image", kwargs={"user_id": "550e8400-e29b-41d4-a716-446655440000"})

        image_file = self.create_upload_file()

        response = self.client.post(url, {"image": image_file}, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("error", response.data)

    @patch("os.path.exists")
    @patch("os.makedirs")
    @patch("builtins.open", new_callable=mock_open)
    @patch("os.remove")
    def test_upload_image_replaces_old_image(self, mock_remove, mock_file, mock_makedirs, mock_exists):
        """Test that uploading a new image removes the old one"""
        mock_exists.side_effect = lambda path: "/images" in path  # Mock directory exists, file exists

        # Set existing image path
        self.user.profile_image_path = "old_image.png"
        self.user.save()

        self.client.force_authenticate(user=self.user)
        url = reverse("user_image", kwargs={"user_id": self.user.id})

        image_file = self.create_upload_file("new_image.png")

        response = self.client.post(url, {"image": image_file}, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Verify both test file and old image removal were attempted
        # Should call remove twice: once for .test_write, once for old_image.png
        self.assertEqual(mock_remove.call_count, 2)
        # Check that both files were removed (use any_order due to OS path differences)
        test_write_called = any(".test_write" in str(call_obj) for call_obj in mock_remove.call_args_list)
        old_image_called = any("old_image.png" in str(call_obj) for call_obj in mock_remove.call_args_list)
        self.assertTrue(test_write_called, "Test write file should be removed")
        self.assertTrue(old_image_called, "Old image file should be removed")

    @patch("os.path.exists")
    def test_get_image_success(self, mock_exists):
        """Test successful image retrieval"""
        # Set up user with existing image
        self.user.profile_image_path = f"{self.user.id}_test.png"
        self.user.save()

        mock_exists.return_value = True

        self.client.force_authenticate(user=self.user)
        url = reverse("user_image", kwargs={"user_id": self.user.id})

        with patch("builtins.open", mock_open(read_data=b"image_data")):
            response = self.client.get(url)
            self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_get_image_no_authentication(self):
        """Test image retrieval without authentication"""
        url = reverse("user_image", kwargs={"user_id": self.user.id})

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_get_image_access_denied(self):
        """Test image retrieval for another user without admin privileges"""
        self.client.force_authenticate(user=self.user)
        url = reverse("user_image", kwargs={"user_id": self.other_user.id})

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch("os.path.exists")
    def test_admin_get_image_for_other_user(self, mock_exists):
        """Test admin can retrieve image for another user"""
        # Set up other user with image
        self.other_user.profile_image_path = f"{self.other_user.id}_test.png"
        self.other_user.save()

        mock_exists.return_value = True

        self.client.force_authenticate(user=self.admin_user)
        url = reverse("user_image", kwargs={"user_id": self.other_user.id})

        with patch("builtins.open", mock_open(read_data=b"image_data")):
            response = self.client.get(url)
            self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_get_image_no_image_path(self):
        """Test image retrieval when user has no image"""
        self.client.force_authenticate(user=self.user)
        url = reverse("user_image", kwargs={"user_id": self.user.id})

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    @patch("os.path.exists")
    def test_get_image_file_not_found(self, mock_exists):
        """Test image retrieval when file doesn't exist on disk"""
        self.user.profile_image_path = "nonexistent_image.png"
        self.user.save()

        mock_exists.return_value = False

        self.client.force_authenticate(user=self.user)
        url = reverse("user_image", kwargs={"user_id": self.user.id})

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_get_image_user_not_found(self):
        """Test image retrieval for non-existent user"""
        self.client.force_authenticate(user=self.admin_user)
        url = reverse("user_image", kwargs={"user_id": "550e8400-e29b-41d4-a716-446655440000"})

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_upload_jpeg_image(self):
        """Test uploading JPEG image"""
        self.client.force_authenticate(user=self.user)
        url = reverse("user_image", kwargs={"user_id": self.user.id})

        jpeg_file = self.create_upload_file("test.jpg", format="JPEG")

        with patch("os.path.exists", return_value=True):
            with patch("os.makedirs"):
                with patch("builtins.open", mock_open()):
                    response = self.client.post(url, {"image": jpeg_file}, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @patch("os.path.exists")
    @patch("os.makedirs")
    def test_upload_image_directory_creation(self, mock_makedirs, mock_exists):
        """Test that images directory is created if it doesn't exist"""
        mock_exists.return_value = False  # Directory doesn't exist

        self.client.force_authenticate(user=self.user)
        url = reverse("user_image", kwargs={"user_id": self.user.id})

        image_file = self.create_upload_file()

        with patch("builtins.open", mock_open()) as mock_file:
            # Mock the open call to simulate permission error for the test file
            def open_side_effect(filename, mode="r"):
                if ".test_write" in filename:
                    raise PermissionError("Permission denied")
                return mock_open().return_value
            
            mock_file.side_effect = open_side_effect
            response = self.client.post(url, {"image": image_file}, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should try to create /images first, then fallback to /tmp/images
        expected_calls = [call("/images", exist_ok=True), call("/tmp/images", exist_ok=True)]
        mock_makedirs.assert_has_calls(expected_calls)

    @patch("os.path.exists")
    def test_get_image_png_content_type(self, mock_exists):
        """Test that PNG images return correct content type"""
        self.user.profile_image_path = f"{self.user.id}_test.png"
        self.user.save()

        mock_exists.return_value = True

        self.client.force_authenticate(user=self.user)
        url = reverse("user_image", kwargs={"user_id": self.user.id})

        with patch("builtins.open", mock_open(read_data=b"image_data")):
            response = self.client.get(url)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            # For PNG files, content type should be image/png
            self.assertEqual(response["Content-Type"], "image/png")

    @patch("os.path.exists")
    def test_get_image_jpeg_content_type(self, mock_exists):
        """Test that JPEG images return correct content type"""
        self.user.profile_image_path = f"{self.user.id}_test.jpg"
        self.user.save()

        mock_exists.return_value = True

        self.client.force_authenticate(user=self.user)
        url = reverse("user_image", kwargs={"user_id": self.user.id})

        with patch("builtins.open", mock_open(read_data=b"image_data")):
            response = self.client.get(url)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            # For JPEG files, content type should be image/jpeg
            self.assertEqual(response["Content-Type"], "image/jpeg")


@pytest.mark.django_db
class TestUserProfileSerializerWithImage:
    """Test that UserProfileSerializer includes profile_image_path"""

    def test_profile_serializer_includes_image_path(self, api_client):
        """Test that profile endpoint returns profile_image_path"""
        company = Company.objects.create(name="Test Company", domain="@testcompany.com")

        user = User.objects.create_user(
            email="testuser@testcompany.com",
            password="testpass123",
            first_name="Test",
            last_name="User",
            company=company,
            profile_image_path="test_image.png",
        )

        api_client.force_authenticate(user=user)
        url = reverse("profile")

        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert "profile_image_path" in response.data
        assert response.data["profile_image_path"] == "test_image.png"

    def test_profile_serializer_null_image_path(self, api_client):
        """Test that profile endpoint handles null profile_image_path"""
        company = Company.objects.create(name="Test Company", domain="@testcompany.com")

        user = User.objects.create_user(
            email="testuser@testcompany.com",
            password="testpass123",
            first_name="Test",
            last_name="User",
            company=company,
            profile_image_path=None,
        )

        api_client.force_authenticate(user=user)
        url = reverse("profile")

        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert "profile_image_path" in response.data
        assert response.data["profile_image_path"] is None
