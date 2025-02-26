def test_generate_uuid():
	from app.shared.db.models import generate_uuid

	assert generate_uuid() != generate_uuid()
	assert len(generate_uuid()) == 36
	assert generate_uuid().count("-") == 4
