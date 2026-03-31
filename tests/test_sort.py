names = [
    "Álvaro",
    "André",
    "Ângelo",
    "Carlos",
    "Çağlar",
    "João",
    "José",
    "Óscar",
    "Zélia",
]

sorted_names = sorted(names)
print("Sorted names:")
for i, name in enumerate(sorted_names):
    print(f"{i}: {name} (starts with '{name[0]}')")

print(f"\nFirst: {sorted_names[0]} (starts with '{sorted_names[0][0]}')")
print(f"Last: {sorted_names[-1]} (starts with '{sorted_names[-1][0]}')")
