from sqlalchemy.orm import Session
from db.models import Ilha, Usuario, BaseApoio, Embarcacao, MembroEquipe, EspacoAmostral
from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

def seed_admin(db: Session):
    existing_user = db.query(Usuario).filter(Usuario.username == "admin").first()
    if existing_user:
        return
        
    admin_user = Usuario(
        username="admin",
        email="admin@bluebell.com",
        senha_hash=pwd_context.hash("admin"),
        nome_completo="Administrador",
        perfil="admin",
        ativo=True
    )
    db.add(admin_user)
    db.commit()

def seed_ilhas(db: Session):
    if db.query(Ilha).count() > 0:
        return
        
    ilhas_data = [
        {"codigo": "IC", "nome": "Ilha das Couves", "coords": (-23.422500, -44.855900)},
        {"codigo": "IA", "nome": "Ilha Anchieta", "coords": (-23.543000, -45.060000)},
        {"codigo": "IV", "nome": "Ilha Vitória", "coords": (-23.750000, -45.017000)},
        {"codigo": "IB", "nome": "Ilha de Búzios", "coords": (-23.804817, -45.157083)},
        {"codigo": "MT", "nome": "Ilha Montão de Trigo", "coords": (-23.860595, -45.775051)},
        {"codigo": "IQG", "nome": "Ilha da Queimada Grande", "coords": (-24.487922, -46.674156)},
        {"codigo": "LC", "nome": "Laje da Conceição", "coords": (-24.236288, -46.690989)},
        {"codigo": "LS", "nome": "Laje de Santos", "coords": (-24.319810, -46.181973)},
        {"codigo": "IMV", "nome": "Ilha do Mar Virado", "coords": (-23.567000, -45.167000)},
        {"codigo": "IMO", "nome": "Ilha da Moela", "coords": (-24.050795, -46.263451)},
        {"codigo": "PC", "nome": "Praia de Castelhanos", "coords": (-23.849436, -45.322978)},
        {"codigo": "IGU", "nome": "Ilha do Guaraú", "coords": (-24.383333, -46.983333)},
        {"codigo": "ICB", "nome": "Ilha das Cabras", "coords": (-23.829400, -45.392600)},
    ]
    
    for item in ilhas_data:
        lat, lon = item["coords"]
        point = Point(lon, lat)
        ilha = Ilha(
            codigo=item["codigo"],
            nome=item["nome"],
            localizacao=from_shape(point, srid=4326),
            descricao=f"Seed data for {item['nome']}"
        )
        db.add(ilha)
    
    db.commit()

def seed_cadastros(db: Session):
    """Seed default bases, vessels and team members"""
    if db.query(BaseApoio).count() > 0:
        return
        
    bases = [
        "Píer Saco da Ribeira – Ilha Anchieta - R. Marginal",
        "Marina Centro Náutico IlhaBela",
        "Marina Capri, São Vicente",
        "Marina Aquarium, São Vicente",
        "Marina UbaUba"
    ]
    
    for nome in bases:
        base = BaseApoio(nome=nome)
        db.add(base)
        
    db.commit()

def seed_espacos_amostrais(db: Session):
    """Seed real station/sampling point data for each island"""
    if db.query(EspacoAmostral).count() > 0:
        return

    # Real station data per island (codigo_ilha -> list of stations)
    stations_data = {
        "IC": [  # Ilha das Couves
            {"codigo": "IC01", "metodologia": "BA", "lat": -23.410360, "lon": -44.853300},
            {"codigo": "IC02", "metodologia": "BA", "lat": -23.417030, "lon": -44.855050},
            {"codigo": "IC03", "metodologia": "FQ e VT", "lat": -23.421800, "lon": -44.855850},
            {"codigo": "IC04", "metodologia": "FQ e VT", "lat": -23.423190, "lon": -44.857970},
            {"codigo": "IC05", "metodologia": "BA", "lat": -23.422500, "lon": -44.859590},
            {"codigo": "IC06", "metodologia": "BA", "lat": -23.425390, "lon": -44.856260},
            {"codigo": "IC07", "metodologia": "BA", "lat": -23.421820, "lon": -44.850520},
            {"codigo": "IC08", "metodologia": "BA", "lat": -23.414710, "lon": -44.853100},
        ],
        "IA": [  # Ilha Anchieta
            {"codigo": "IA01", "metodologia": "BA", "lat": -23.527830, "lon": -45.057420},
            {"codigo": "IA02", "metodologia": "BA", "lat": -23.531130, "lon": -45.047460},
            {"codigo": "IA03", "metodologia": "BA", "lat": -23.533630, "lon": -45.038790},
            {"codigo": "IA04", "metodologia": "BA", "lat": -23.546290, "lon": -45.054870},
            {"codigo": "IA05", "metodologia": "BA", "lat": -23.561180, "lon": -45.074870},
            {"codigo": "IA06", "metodologia": "BA", "lat": -23.553090, "lon": -45.080620},
            {"codigo": "IA07", "metodologia": "FQ e VT", "lat": -23.549290, "lon": -45.079890},
            {"codigo": "IA08", "metodologia": "FQ e VT", "lat": -23.533660, "lon": -45.080620},
        ],
        "IV": [  # Ilha Vitória
            {"codigo": "IV01", "metodologia": "FQ e VT", "lat": -23.752370, "lon": -45.017540},
            {"codigo": "IV02", "metodologia": "FQ e VT", "lat": -23.748210, "lon": -45.010550},
        ],
        "IB": [  # Ilha de Búzios
            {"codigo": "IB01", "metodologia": "FQ e VT", "lat": -23.797580, "lon": -45.155840},
            {"codigo": "IB02", "metodologia": "FQ e VT", "lat": -23.802390, "lon": -45.119730},
        ],
        "MT": [  # Ilha Montão de Trigo
            {"codigo": "MT01", "metodologia": "BA", "lat": -23.858650, "lon": -45.780540},
            {"codigo": "MT02", "metodologia": "BA", "lat": -23.861880, "lon": -45.773760},
            {"codigo": "MT03", "metodologia": "BA", "lat": -23.867300, "lon": -45.775040},
            {"codigo": "MT04", "metodologia": "BA", "lat": -23.870030, "lon": -45.778950},
            {"codigo": "MT05", "metodologia": "BA", "lat": -23.869530, "lon": -45.785850},
            {"codigo": "MT06", "metodologia": "BA", "lat": -23.863790, "lon": -45.787360},
            {"codigo": "MT07", "metodologia": "FQ e VT", "lat": -23.860130, "lon": -45.786260},
            {"codigo": "MT08", "metodologia": "FQ e VT", "lat": None, "lon": None},
        ],
        "IQG": [  # Ilha da Queimada Grande
            {"codigo": "IQG01", "metodologia": "BA", "lat": -24.477470, "lon": -46.675330},
            {"codigo": "IQG02", "metodologia": "BA", "lat": -24.483050, "lon": -46.677750},
            {"codigo": "IQG03", "metodologia": "BA", "lat": -24.489440, "lon": -46.677440},
            {"codigo": "IQG04", "metodologia": "BA", "lat": -24.491480, "lon": -46.677960},
            {"codigo": "IQG05", "metodologia": "BA", "lat": -24.489390, "lon": -46.670470},
            {"codigo": "IQG06", "metodologia": "BA", "lat": -24.481600, "lon": -46.674470},
            {"codigo": "IQG07", "metodologia": "FQ e VT", "lat": -24.484110, "lon": -46.673250},
            {"codigo": "IQG08", "metodologia": "FQ e VT", "lat": None, "lon": None},
        ],
        "LC": [  # Laje da Conceição
            {"codigo": "LC01", "metodologia": "BA", "lat": -24.236810, "lon": -46.691060},
            {"codigo": "LC02", "metodologia": "BA", "lat": -24.237270, "lon": -46.690950},
            {"codigo": "LC03", "metodologia": "BA", "lat": -24.237490, "lon": -46.690070},
            {"codigo": "LC04", "metodologia": "BA", "lat": -24.236820, "lon": -46.690160},
            {"codigo": "LC05", "metodologia": "FQ e VT", "lat": None, "lon": None},
            {"codigo": "LC06", "metodologia": "FQ e VT", "lat": None, "lon": None},
        ],
        "LS": [  # Laje de Santos
            {"codigo": "LS01", "metodologia": "BA", "lat": -24.318450, "lon": -46.181130},
            {"codigo": "LS02", "metodologia": "BA", "lat": -24.320440, "lon": -46.183330},
            {"codigo": "LS03", "metodologia": "BA", "lat": -24.320240, "lon": -46.181450},
            {"codigo": "LS04", "metodologia": "BA", "lat": -24.327890, "lon": -46.161450},
            {"codigo": "LS05", "metodologia": "FQ e VT", "lat": -24.319410, "lon": -46.182070},
            {"codigo": "LS06", "metodologia": "FQ e VT", "lat": -24.329180, "lon": -46.162520},
        ],
        "IMV": [  # Ilha do Mar Virado
            {"codigo": "IMV01", "metodologia": "BA", "lat": -23.564300, "lon": -45.160800},
            {"codigo": "IMV02", "metodologia": "BA", "lat": -23.561780, "lon": -45.158470},
            {"codigo": "IMV03", "metodologia": "BA", "lat": None, "lon": None},
            {"codigo": "IMV04", "metodologia": "BA", "lat": None, "lon": None},
        ],
        "IMO": [  # Ilha da Moela
            {"codigo": "IMO01", "metodologia": "BA", "lat": -24.051630, "lon": -46.265250},
            {"codigo": "IMO02", "metodologia": "BA", "lat": -24.048240, "lon": -46.264750},
            {"codigo": "IMO03", "metodologia": "BA", "lat": -24.044710, "lon": -46.260610},
            {"codigo": "IMO04", "metodologia": "BA", "lat": -24.049370, "lon": -46.261700},
        ],
        "PC": [  # Praia de Castelhanos
            {"codigo": "PC01", "metodologia": "BA", "lat": -23.837910, "lon": -45.268340},
            {"codigo": "PC02", "metodologia": "BA", "lat": -23.848590, "lon": -45.280690},
            {"codigo": "PC03", "metodologia": "BA", "lat": -23.850140, "lon": -45.282020},
            {"codigo": "PC04", "metodologia": "BA", "lat": -23.861810, "lon": -45.286190},
            {"codigo": "PC05", "metodologia": "BA", "lat": -23.864200, "lon": -45.285630},
            {"codigo": "PC06", "metodologia": "BA", "lat": -23.873000, "lon": -45.286490},
        ],
        "IGU": [  # Ilha do Guaraú
            {"codigo": "IGU01", "metodologia": "BA", "lat": -24.383580, "lon": -46.988030},
            {"codigo": "IGU02", "metodologia": "BA", "lat": -24.382150, "lon": -46.986930},
            {"codigo": "IGU03", "metodologia": "BA", "lat": -24.379360, "lon": -46.985540},
            {"codigo": "IGU04", "metodologia": "BA", "lat": -24.381860, "lon": -46.983900},
        ],
        "ICB": [  # Ilha das Cabras
            {"codigo": "ICB01", "metodologia": "BA", "lat": -23.830260, "lon": -45.392980},
            {"codigo": "ICB02", "metodologia": "BA", "lat": -23.829650, "lon": -45.393480},
            {"codigo": "ICB03", "metodologia": "BA", "lat": -23.828940, "lon": -45.393000},
            {"codigo": "ICB04", "metodologia": "BA", "lat": -23.828910, "lon": -45.391700},
            {"codigo": "ICB05", "metodologia": "FQ e VT", "lat": None, "lon": None},
            {"codigo": "ICB06", "metodologia": "FQ e VT", "lat": None, "lon": None},
        ],
    }

    # Map island codes to DB IDs
    ilhas = db.query(Ilha).all()
    ilha_map = {ilha.codigo: ilha.id for ilha in ilhas}

    for codigo_ilha, stations in stations_data.items():
        ilha_id = ilha_map.get(codigo_ilha)
        if not ilha_id:
            print(f"⚠️ Ilha com código '{codigo_ilha}' não encontrada no banco, pulando...")
            continue

        for st in stations:
            ea = EspacoAmostral(
                ilha_id=ilha_id,
                codigo=st["codigo"],
                nome=st["codigo"],  # Use code as display name
                metodologia=st["metodologia"],
                latitude=st["lat"],
                longitude=st["lon"],
                descricao=f"Estação {st['codigo']} - {st['metodologia']}"
            )
            db.add(ea)

    db.commit()
    print(f"✓ {db.query(EspacoAmostral).count()} estações amostrais inseridas")

