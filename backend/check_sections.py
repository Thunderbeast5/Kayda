from lexigraphbe.statute_repository import StatuteRepository

StatuteRepository.reset_instance()
repo = StatuteRepository.get_instance()

print(f"Total sections loaded: {len(repo.get_sections_db())}\n")
print("All sections:")
for s in repo.get_sections_db():
    print(f"  {s['statute']} {s['section_number']}: {s['title'][:60]}")

print("\n318 present?", any(s['section_number'] == '318' for s in repo.get_sections_db()))
