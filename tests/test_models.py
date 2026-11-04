from backend.models import RefreshToken, User, UserIntegration, UserProfile, UserResumeFile


def test_auth_foundation_models_are_mapped():
    assert {
        User.__tablename__,
        RefreshToken.__tablename__,
        UserProfile.__tablename__,
        UserResumeFile.__tablename__,
        UserIntegration.__tablename__,
    } == {"users", "refresh_tokens", "user_profiles", "user_resume_files", "user_integrations"}
