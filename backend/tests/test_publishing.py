"""
Unit tests for publishing API endpoints
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

def test_get_public_scenarios(client: TestClient, test_scenario):
    """Test get public scenarios for marketplace"""
    response = client.get("/publishing/scenarios")
    assert response.status_code == 200
    
    data = response.json()
    assert isinstance(data, list)
    # Should only show public scenarios
    for scenario in data:
        assert scenario["is_public"] == True

def test_get_public_scenarios_with_filters(client: TestClient, test_scenario):
    """Test get public scenarios with filters"""
    response = client.get("/publishing/scenarios?category=Technology&difficulty=beginner")
    assert response.status_code == 200
    
    data = response.json()
    assert isinstance(data, list)

def test_get_public_scenarios_with_pagination(client: TestClient, test_scenario):
    """Test get public scenarios with pagination"""
    response = client.get("/publishing/scenarios?page=1&page_size=10")
    assert response.status_code == 200
    
    data = response.json()
    assert isinstance(data, list)

def test_get_scenario_details(client: TestClient, test_scenario):
    """Test get scenario details for publishing"""
    response = client.get(f"/publishing/scenarios/{test_scenario.id}")
    assert response.status_code == 200
    
    data = response.json()
    assert data["id"] == test_scenario.id
    assert data["title"] == test_scenario.title
    assert "rating_avg" in data
    assert "rating_count" in data

def test_get_scenario_details_not_found(client: TestClient):
    """Test get non-existent scenario details"""
    response = client.get("/publishing/scenarios/99999")
    assert response.status_code == 404
    assert "Scenario not found" in response.json()["detail"]

def test_publish_scenario(client: TestClient, auth_headers_professor, test_scenario):
    """Test publish scenario"""
    publish_data = {
        "is_public": True,
        "category": "Leadership",
        "difficulty_level": "intermediate",
        "tags": ["leadership", "management"]
    }
    
    response = client.put(f"/publishing/scenarios/{test_scenario.id}/publish", json=publish_data, headers=auth_headers_professor)
    assert response.status_code == 200
    
    data = response.json()
    assert data["is_public"] == True
    assert data["category"] == publish_data["category"]

def test_publish_scenario_unauthorized(client: TestClient, auth_headers_student, test_scenario):
    """Test publish scenario as student"""
    publish_data = {
        "is_public": True,
        "category": "Leadership"
    }
    
    response = client.put(f"/publishing/scenarios/{test_scenario.id}/publish", json=publish_data, headers=auth_headers_student)
    assert response.status_code == 403

def test_unpublish_scenario(client: TestClient, auth_headers_professor, test_scenario):
    """Test unpublish scenario"""
    response = client.put(f"/publishing/scenarios/{test_scenario.id}/unpublish", headers=auth_headers_professor)
    assert response.status_code == 200
    
    data = response.json()
    assert data["is_public"] == False

def test_rate_scenario(client: TestClient, auth_headers_student, test_scenario):
    """Test rate scenario"""
    rating_data = {
        "rating": 5,
        "review": "Great scenario!"
    }
    
    response = client.post(f"/publishing/scenarios/{test_scenario.id}/rate", json=rating_data, headers=auth_headers_student)
    assert response.status_code == 200
    
    data = response.json()
    assert data["rating"] == rating_data["rating"]
    assert data["review"] == rating_data["review"]

def test_rate_scenario_invalid_rating(client: TestClient, auth_headers_student, test_scenario):
    """Test rate scenario with invalid rating"""
    rating_data = {
        "rating": 6,  # Invalid rating (should be 1-5)
        "review": "Invalid rating"
    }
    
    response = client.post(f"/publishing/scenarios/{test_scenario.id}/rate", json=rating_data, headers=auth_headers_student)
    assert response.status_code == 400
    assert "Rating must be between 1 and 5" in response.json()["detail"]

def test_get_scenario_reviews(client: TestClient, test_scenario):
    """Test get scenario reviews"""
    response = client.get(f"/publishing/scenarios/{test_scenario.id}/reviews")
    assert response.status_code == 200
    
    data = response.json()
    assert isinstance(data, list)

def test_get_scenario_reviews_with_pagination(client: TestClient, test_scenario):
    """Test get scenario reviews with pagination"""
    response = client.get(f"/publishing/scenarios/{test_scenario.id}/reviews?page=1&page_size=5")
    assert response.status_code == 200
    
    data = response.json()
    assert isinstance(data, list)

def test_get_scenario_categories(client: TestClient):
    """Test get scenario categories"""
    response = client.get("/publishing/categories")
    assert response.status_code == 200
    
    data = response.json()
    assert "categories" in data
    assert "predefined" in data
    assert isinstance(data["categories"], list)
    assert isinstance(data["predefined"], list)

def test_get_difficulty_levels(client: TestClient):
    """Test get difficulty levels"""
    response = client.get("/publishing/difficulty-levels")
    assert response.status_code == 200
    
    data = response.json()
    assert "levels" in data
    assert isinstance(data["levels"], list)

def test_search_scenarios(client: TestClient, test_scenario):
    """Test search scenarios"""
    response = client.get("/publishing/scenarios/search?q=test")
    assert response.status_code == 200
    
    data = response.json()
    assert isinstance(data, list)

def test_search_scenarios_with_filters(client: TestClient, test_scenario):
    """Test search scenarios with filters"""
    response = client.get("/publishing/scenarios/search?q=test&category=Technology&difficulty=beginner")
    assert response.status_code == 200
    
    data = response.json()
    assert isinstance(data, list)

def test_get_featured_scenarios(client: TestClient, test_scenario):
    """Test get featured scenarios"""
    response = client.get("/publishing/scenarios/featured")
    assert response.status_code == 200
    
    data = response.json()
    assert isinstance(data, list)

def test_get_trending_scenarios(client: TestClient, test_scenario):
    """Test get trending scenarios"""
    response = client.get("/publishing/scenarios/trending")
    assert response.status_code == 200
    
    data = response.json()
    assert isinstance(data, list)

def test_get_scenario_stats(client: TestClient, auth_headers_professor, test_scenario):
    """Test get scenario statistics"""
    response = client.get(f"/publishing/scenarios/{test_scenario.id}/stats", headers=auth_headers_professor)
    assert response.status_code == 200
    
    data = response.json()
    assert "views" in data
    assert "downloads" in data
    assert "ratings" in data

def test_get_scenario_stats_unauthorized(client: TestClient, auth_headers_student, test_scenario):
    """Test get scenario statistics as student"""
    response = client.get(f"/publishing/scenarios/{test_scenario.id}/stats", headers=auth_headers_student)
    assert response.status_code == 403

def test_update_scenario_visibility(client: TestClient, auth_headers_professor, test_scenario):
    """Test update scenario visibility"""
    visibility_data = {
        "is_public": False,
        "visibility_reason": "Under review"
    }
    
    response = client.put(f"/publishing/scenarios/{test_scenario.id}/visibility", json=visibility_data, headers=auth_headers_professor)
    assert response.status_code == 200
    
    data = response.json()
    assert data["is_public"] == False

def test_get_user_published_scenarios(client: TestClient, auth_headers_professor, test_scenario):
    """Test get user's published scenarios"""
    response = client.get("/publishing/my-scenarios", headers=auth_headers_professor)
    assert response.status_code == 200
    
    data = response.json()
    assert isinstance(data, list)

def test_get_user_published_scenarios_unauthorized(client: TestClient):
    """Test get user's published scenarios without authentication"""
    response = client.get("/publishing/my-scenarios")
    assert response.status_code == 401

