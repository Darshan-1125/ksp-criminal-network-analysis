import random
import datetime
from faker import Faker
from sqlalchemy.orm import Session
from app.db import SessionLocal, Base, engine
from app.models import District, PoliceStation, Location, Accused, Victim, FIRCase, CaseEmbedding

fake = Faker('en_IN')

# Seed districts
DISTRICTS = [
    "Mysuru", "Bengaluru Urban", "Belagavi", "Mangaluru", "Mandya",
    "Kolar", "Udupi", "Shivamogga", "Ballari", "Tumakuru"
]

CRIME_TYPES = [
    "Robbery", "Theft", "Murder", "Assault", "Cybercrime",
    "Extortion", "Burglary", "Kidnapping", "Drug Trafficking", "Cheating"
]

IPC_SECTIONS_MAP = {
    "Robbery": "392, 397",
    "Theft": "379",
    "Murder": "302",
    "Assault": "323, 324",
    "Cybercrime": "IT Act 66D",
    "Extortion": "384",
    "Burglary": "457, 380",
    "Kidnapping": "363",
    "Drug Trafficking": "NDPS Act 20",
    "Cheating": "420"
}

def seed_db():
    print("Seeding database...")
    db = SessionLocal()
    
    # Reset tables
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    
    # 1. Create Districts
    district_objs = []
    for name in DISTRICTS:
        d = District(name=name)
        db.add(d)
        district_objs.append(d)
    db.commit()
    
    # 2. Create Police Stations
    ps_objs = []
    for dist in district_objs:
        # Create 3 police stations per district
        for i in range(1, 4):
            ps = PoliceStation(name=f"{dist.name} PS-{i}", district_id=dist.id)
            db.add(ps)
            ps_objs.append(ps)
    db.commit()
    
    # 3. Create Locations
    locations = []
    for dist in district_objs:
        # Generate 15 locations per district
        for _ in range(15):
            loc = Location(
                address=fake.street_address(),
                city=dist.name,
                district_id=dist.id,
                latitude=float(fake.latitude()),
                longitude=float(fake.longitude())
            )
            db.add(loc)
            locations.append(loc)
    db.commit()
    
    # 4. Create Accused
    accused_objs = []
    
    # Seed Repeat Offenders (accused_id 1, 2, 3)
    repeat_offender_1 = Accused(
        name="Ravi Kumar",
        age=32,
        gender="Male",
        phone="9886012345",
        address="12, 1st Cross, Hebbal, Bengaluru",
        photo_url="https://images.unsplash.com/photo-1500648767791-00dcc994a43e"
    )
    repeat_offender_2 = Accused(
        name="Darshan S.",
        age=28,
        gender="Male",
        phone="9845098765",
        address="45, MG Road, Mysuru",
        photo_url="https://images.unsplash.com/photo-1535713875002-d1d0cf377fde"
    )
    repeat_offender_3 = Accused(
        name="Kiran K.",
        age=35,
        gender="Male",
        phone="9741002233",
        address="9, Kolar Town, Kolar",
        photo_url="https://images.unsplash.com/photo-1570295999919-56ceb5ecca61"
    )
    db.add_all([repeat_offender_1, repeat_offender_2, repeat_offender_3])
    accused_objs.extend([repeat_offender_1, repeat_offender_2, repeat_offender_3])
    
    # Seed Organized Crime Network (5 accused sharing address and phone number)
    shared_phone = "9900112233"
    shared_address = "No. 42, 2nd Cross, Rajajinagar, Bengaluru"
    network_members = [
        ("Vijay Prasad", 29),
        ("Anand Shetty", 31),
        ("Ramesh Gowda", 27),
        ("Suresh Naik", 34),
        ("Santosh Poojary", 33)
    ]
    network_objs = []
    for name, age in network_members:
        member = Accused(
            name=name,
            age=age,
            gender="Male",
            phone=shared_phone,
            address=shared_address,
            photo_url=f"https://images.unsplash.com/photo-{random.randint(1500000000, 1600000000)}"
        )
        db.add(member)
        network_objs.append(member)
    db.commit()
    accused_objs.extend(network_objs)
    
    # Seed random accused
    for _ in range(80):
        acc = Accused(
            name=fake.name_male() if random.random() > 0.1 else fake.name_female(),
            age=random.randint(18, 65),
            gender="Male" if random.random() > 0.1 else "Female",
            phone=f"9{random.randint(10000000, 99999999)}",
            address=fake.address(),
            photo_url=None
        )
        db.add(acc)
        accused_objs.append(acc)
    db.commit()
    
    # 5. Create Victims
    victim_objs = []
    for _ in range(150):
        vic = Victim(
            name=fake.name(),
            age=random.randint(10, 80),
            gender="Female" if random.random() > 0.4 else "Male",
            phone=f"9{random.randint(10000000, 99999999)}",
            address=fake.address()
        )
        db.add(vic)
        victim_objs.append(vic)
    db.commit()
    
    # 6. Create FIR Cases (500 cases)
    # First, let's create specific narratives for repeat offenders and networks
    fir_cases = []
    
    # Helper to generate dates in 2024-2025
    def gen_random_date():
        start_date = datetime.date(2024, 1, 1)
        end_date = datetime.date(2025, 12, 31)
        time_between_dates = end_date - start_date
        days_between_dates = time_between_dates.days
        random_number_of_days = random.randrange(days_between_dates)
        return start_date + datetime.timedelta(days=random_number_of_days)

    # Add case for Repeat Offender 1 in Mysuru
    case_ro1_1 = FIRCase(
        fir_number="KA-2024-1123",
        crime_type="Robbery",
        ipc_sections=IPC_SECTIONS_MAP["Robbery"],
        district_id=district_objs[0].id, # Mysuru
        police_station_id=ps_objs[0].id, # Mysuru PS-1
        location_id=locations[0].id,
        date_reported=datetime.date(2024, 11, 2),
        status="under_investigation",
        mo_description="Armed robbery, night, motorcycle escape",
        narrative="The accused came on a black motorcycle, brandished a knife, and demanded the victim hand over their gold chain. The incident happened near MG Road at night.",
        latitude=12.2958,
        longitude=76.6394
    )
    case_ro1_1.accused.append(repeat_offender_1)
    case_ro1_1.victims.append(victim_objs[0])
    db.add(case_ro1_1)
    fir_cases.append(case_ro1_1)
    
    # Add near-identical case (Pair 1 - Belagavi) for similarity search demo
    case_ro1_2 = FIRCase(
        fir_number="KA-2024-1188",
        crime_type="Robbery",
        ipc_sections=IPC_SECTIONS_MAP["Robbery"],
        district_id=district_objs[2].id, # Belagavi
        police_station_id=ps_objs[6].id, # Belagavi PS-1
        location_id=locations[30].id,
        date_reported=datetime.date(2024, 11, 15),
        status="under_investigation",
        mo_description="Armed robbery, night, motorcycle escape",
        narrative="The accused came on a black motorcycle, brandished a knife, and demanded the victim hand over their gold chain. The incident happened near MG Road at night.",
        latitude=15.8528,
        longitude=74.5042
    )
    case_ro1_2.accused.append(repeat_offender_1) # repeat offender in another district!
    case_ro1_2.victims.append(victim_objs[1])
    db.add(case_ro1_2)
    fir_cases.append(case_ro1_2)

    # Near-identical case Pair 2 (Cybercrime)
    case_cyber_1 = FIRCase(
        fir_number="KA-2025-0987",
        crime_type="Cybercrime",
        ipc_sections=IPC_SECTIONS_MAP["Cybercrime"],
        district_id=district_objs[1].id, # Bengaluru Urban
        police_station_id=ps_objs[3].id, # Bengaluru PS-1
        location_id=locations[15].id,
        date_reported=datetime.date(2025, 3, 10),
        status="under_investigation",
        mo_description="Phishing, electricity bill scam",
        narrative="A cyber fraud incident occurred where the victim received a phishing link claiming to be from the Electricity Board. After clicking, funds were unauthorizedly debited.",
        latitude=12.9716,
        longitude=77.5946
    )
    case_cyber_1.accused.append(repeat_offender_3)
    case_cyber_1.victims.append(victim_objs[2])
    db.add(case_cyber_1)
    fir_cases.append(case_cyber_1)
    
    case_cyber_2 = FIRCase(
        fir_number="KA-2025-1044",
        crime_type="Cybercrime",
        ipc_sections=IPC_SECTIONS_MAP["Cybercrime"],
        district_id=district_objs[3].id, # Mangaluru
        police_station_id=ps_objs[9].id, # Mangaluru PS-1
        location_id=locations[45].id,
        date_reported=datetime.date(2025, 3, 18),
        status="under_investigation",
        mo_description="Phishing, electricity bill scam",
        narrative="A cyber fraud incident occurred where the victim received a phishing link claiming to be from the Electricity Board. After clicking, funds were unauthorizedly debited.",
        latitude=12.9141,
        longitude=74.8560
    )
    # Add one of the network members as the cyber accused
    case_cyber_2.accused.append(network_objs[0])
    case_cyber_2.victims.append(victim_objs[3])
    db.add(case_cyber_2)
    fir_cases.append(case_cyber_2)

    # Add network cases to link the cluster of 5 accused
    # Vijay and Anand share a burglary case
    case_net_1 = FIRCase(
        fir_number="KA-2024-5501",
        crime_type="Burglary",
        ipc_sections=IPC_SECTIONS_MAP["Burglary"],
        district_id=district_objs[1].id, # Bengaluru Urban
        police_station_id=ps_objs[4].id,
        location_id=locations[16].id,
        date_reported=datetime.date(2024, 5, 20),
        status="under_investigation",
        mo_description="Shoplifting and break-in at electronic store",
        narrative="Electronic store break-in during the early hours of Monday. Store locks were cut using heavy metal cutters. Mobil phones and laptops worth 5 lakhs stolen.",
        latitude=12.9800,
        longitude=77.6000
    )
    case_net_1.accused.extend([network_objs[0], network_objs[1]])
    case_net_1.victims.append(victim_objs[4])
    db.add(case_net_1)
    fir_cases.append(case_net_1)
    
    # Anand and Ramesh share extortion case
    case_net_2 = FIRCase(
        fir_number="KA-2024-5502",
        crime_type="Extortion",
        ipc_sections=IPC_SECTIONS_MAP["Extortion"],
        district_id=district_objs[1].id, # Bengaluru Urban
        police_station_id=ps_objs[5].id,
        location_id=locations[17].id,
        date_reported=datetime.date(2024, 6, 12),
        status="closed",
        mo_description="Blackmailing business owners for protection money",
        narrative="Multiple local shopkeepers reported threats of violence if protection money was not paid weekly. Accused demanded cash payments.",
        latitude=12.9900,
        longitude=77.6100
    )
    case_net_2.accused.extend([network_objs[1], network_objs[2]])
    case_net_2.victims.append(victim_objs[5])
    db.add(case_net_2)
    fir_cases.append(case_net_2)

    # Ramesh, Suresh, Santosh share drug trafficking case
    case_net_3 = FIRCase(
        fir_number="KA-2024-5503",
        crime_type="Drug Trafficking",
        ipc_sections=IPC_SECTIONS_MAP["Drug Trafficking"],
        district_id=district_objs[3].id, # Mangaluru
        police_station_id=ps_objs[10].id,
        location_id=locations[46].id,
        date_reported=datetime.date(2024, 8, 5),
        status="under_investigation",
        mo_description="Ganja smuggling near college campuses",
        narrative="Accused caught red-handed carrying commercial quantities of ganja in a utility vehicle during a routine checkpoint stop.",
        latitude=12.9200,
        longitude=74.8600
    )
    case_net_3.accused.extend([network_objs[2], network_objs[3], network_objs[4]])
    case_net_3.victims.append(victim_objs[6])
    db.add(case_net_3)
    fir_cases.append(case_net_3)

    # Now generate the rest of the 500 cases randomly
    for i in range(1, 494):
        crime = random.choice(CRIME_TYPES)
        dist = random.choice(district_objs)
        # Filter police stations for this district
        dist_ps = [p for p in ps_objs if p.district_id == dist.id]
        ps = random.choice(dist_ps)
        # Filter locations for this district
        dist_locs = [l for l in locations if l.district_id == dist.id]
        loc = random.choice(dist_locs)
        
        fir_num = f"KA-2024-{1200 + i}" if random.random() > 0.3 else f"KA-2025-{1200 + i}"
        
        # Simple descriptions
        mo = f"{crime} reported during {random.choice(['daytime', 'nighttime', 'early hours'])} using {random.choice(['force', 'deception', 'weapon'])}."
        narrative = f"A case of {crime.lower()} was registered at {ps.name} on {fake.date_this_year()}. " \
                    f"The incident occurred near {loc.address} in {dist.name}. " \
                    f"The investigation is ongoing, and officers are gathering evidence."
                    
        case = FIRCase(
            fir_number=fir_num,
            crime_type=crime,
            ipc_sections=IPC_SECTIONS_MAP[crime],
            district_id=dist.id,
            police_station_id=ps.id,
            location_id=loc.id,
            date_reported=gen_random_date(),
            status=random.choice(["under_investigation", "closed", "charge_sheeted"]),
            mo_description=mo,
            narrative=narrative,
            latitude=loc.latitude,
            longitude=loc.longitude
        )
        
        # Add 1-2 random accused
        num_acc = random.randint(1, 2)
        random_acc = random.sample(accused_objs, num_acc)
        case.accused.extend(random_acc)
        
        # Add 1 random victim
        case.victims.append(random.choice(victim_objs))
        
        db.add(case)
        fir_cases.append(case)
        
    db.commit()
    print(f"Successfully seeded {len(fir_cases)} FIR cases!")
    db.close()

if __name__ == "__main__":
    seed_db()
