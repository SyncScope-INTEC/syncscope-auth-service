import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status

from apps.authentication.models import SupervisedUser

User = get_user_model()


@pytest.mark.django_db
class TestSupervisedUserAPI:

    def test_create_supervised_user_relationship_success(self, supervisor_authenticated_client, user, supervisor_user):
        """Test successful creation of supervision relationship"""
        url = reverse("supervised_users")
        data = {"user_id": str(user.id), "supervisor_id": str(supervisor_user.id), "monitoring_enabled": True}

        response = supervisor_authenticated_client.post(url, data)

        assert response.status_code == status.HTTP_201_CREATED
        assert "id" in response.data
        assert response.data["user"]["id"] == str(user.id)
        assert response.data["supervisor"]["id"] == str(supervisor_user.id)
        assert response.data["monitoring_enabled"] is True

        # Check database
        supervised_user = SupervisedUser.objects.get(id=response.data["id"])
        assert supervised_user.user == user
        assert supervised_user.supervisor == supervisor_user
        assert supervised_user.monitoring_enabled is True

    def test_create_supervised_user_self_supervision_fails(self, supervisor_authenticated_client, supervisor_user):
        """Test that users cannot supervise themselves"""
        url = reverse("supervised_users")
        data = {"user_id": str(supervisor_user.id), "supervisor_id": str(supervisor_user.id), "monitoring_enabled": True}

        response = supervisor_authenticated_client.post(url, data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "cannot supervise themselves" in str(response.data)

    def test_create_supervised_user_developer_forbidden(self, authenticated_client, user, supervisor_user):
        """Test that developers cannot create supervision relationships"""
        url = reverse("supervised_users")
        data = {"user_id": str(user.id), "supervisor_id": str(supervisor_user.id), "monitoring_enabled": True}

        response = authenticated_client.post(url, data)

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_supervised_user_invalid_supervisor_role(self, admin_authenticated_client, user, company):
        """Test that only users with supervisor/admin roles can be supervisors"""
        # Create a developer user to try to use as supervisor
        developer = User.objects.create_user(
            email="developer2@testcompany.com",
            password="testpass123",
            first_name="Dev",
            last_name="User",
            role="developer",
            company=company,
        )

        url = reverse("supervised_users")
        data = {"user_id": str(user.id), "supervisor_id": str(developer.id), "monitoring_enabled": True}

        response = admin_authenticated_client.post(url, data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "must have admin or supervisor role" in str(response.data)

    def test_create_duplicate_supervision_relationship_fails(
        self, supervisor_authenticated_client, supervised_user_relationship
    ):
        """Test that duplicate supervision relationships are not allowed"""
        url = reverse("supervised_users")
        data = {
            "user_id": str(supervised_user_relationship.user.id),
            "supervisor_id": str(supervised_user_relationship.supervisor.id),
            "monitoring_enabled": True,
        }

        response = supervisor_authenticated_client.post(url, data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "already exists" in str(response.data)

    def test_list_supervised_users_as_supervisor(self, supervisor_authenticated_client, supervised_user_relationship):
        """Test supervisor can list their supervised users"""
        url = reverse("supervised_users")

        response = supervisor_authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]["id"] == str(supervised_user_relationship.id)

    def test_list_supervised_users_as_admin(self, admin_authenticated_client, supervised_user_relationship):
        """Test admin can see all supervision relationships in company"""
        url = reverse("supervised_users")

        response = admin_authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1

    def test_list_supervised_users_as_developer(self, authenticated_client, supervised_user_relationship):
        """Test developer can see their own supervision relationships"""
        url = reverse("supervised_users")

        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]["user"]["id"] == str(supervised_user_relationship.user.id)

    def test_get_supervised_user_detail(self, supervisor_authenticated_client, supervised_user_relationship):
        """Test retrieving supervision relationship details"""
        url = reverse("supervised_user_detail", kwargs={"pk": supervised_user_relationship.id})

        response = supervisor_authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["id"] == str(supervised_user_relationship.id)
        assert response.data["monitoring_enabled"] is True

    def test_update_supervised_user_monitoring(self, supervisor_authenticated_client, supervised_user_relationship):
        """Test updating monitoring settings"""
        url = reverse("supervised_user_detail", kwargs={"pk": supervised_user_relationship.id})
        data = {"monitoring_enabled": False}

        response = supervisor_authenticated_client.put(url, data)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["monitoring_enabled"] is False

        # Check database
        supervised_user_relationship.refresh_from_db()
        assert supervised_user_relationship.monitoring_enabled is False

    def test_delete_supervised_user_relationship(self, supervisor_authenticated_client, supervised_user_relationship):
        """Test deleting supervision relationship"""
        url = reverse("supervised_user_detail", kwargs={"pk": supervised_user_relationship.id})

        response = supervisor_authenticated_client.delete(url)

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not SupervisedUser.objects.filter(id=supervised_user_relationship.id).exists()

    def test_supervised_user_detail_not_found(self, supervisor_authenticated_client):
        """Test accessing non-existent supervision relationship"""
        import uuid

        fake_id = uuid.uuid4()
        url = reverse("supervised_user_detail", kwargs={"pk": fake_id})

        response = supervisor_authenticated_client.get(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_supervised_user_detail_permission_denied(self, authenticated_client, supervisor_user, company):
        """Test that users cannot access supervision relationships they're not involved in"""
        # Create another user and supervision relationship
        other_user = User.objects.create_user(
            email="other@testcompany.com",
            password="testpass123",
            first_name="Other",
            last_name="User",
            role="developer",
            company=company,
        )

        other_supervised = SupervisedUser.objects.create(user=other_user, supervisor=supervisor_user, monitoring_enabled=True)

        url = reverse("supervised_user_detail", kwargs={"pk": other_supervised.id})

        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_developer_cannot_update_supervision_relationship(self, authenticated_client, supervised_user_relationship):
        """Test that developers cannot update supervision relationships"""
        url = reverse("supervised_user_detail", kwargs={"pk": supervised_user_relationship.id})
        data = {"monitoring_enabled": False}

        response = authenticated_client.put(url, data)

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_developer_cannot_delete_supervision_relationship(self, authenticated_client, supervised_user_relationship):
        """Test that developers cannot delete supervision relationships"""
        url = reverse("supervised_user_detail", kwargs={"pk": supervised_user_relationship.id})

        response = authenticated_client.delete(url)

        assert response.status_code == status.HTTP_403_FORBIDDEN
