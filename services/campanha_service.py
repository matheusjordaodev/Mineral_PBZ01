"""
Campaign Service - Business logic for campaign operations
"""

from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any
import json


class CampanhaService:
    """Service for campaign-related operations"""
    
    def __init__(self, upload_dir: Path):
        self.upload_dir = upload_dir
    
    def create_campanha(self, ilha_id: str, nome: str, data: str, descricao: str = "", custom_id: str = None) -> Dict[str, Any]:
        """Create a new campaign"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if custom_id:
            campanha_id = custom_id
        else:
            campanha_id = f"{nome.lower().replace(' ', '_')}_{timestamp}"
        
        # Create directories
        campanha_path = self.upload_dir / ilha_id / campanha_id
        (campanha_path / "geospatial").mkdir(parents=True, exist_ok=True)
        (campanha_path / "media").mkdir(parents=True, exist_ok=True)
        
        # Save metadata
        metadata = {
            "id": campanha_id,
            "ilha_id": ilha_id,
            "nome": nome,
            "data": data,
            "descricao": descricao,
            "criado_em": timestamp
        }
        
        with open(campanha_path / "metadata.json", 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        
        return metadata
    
    def get_campanhas(self, ilha_id: str) -> List[Dict[str, Any]]:
        """Get all campaigns for an island"""
        ilha_dir = self.upload_dir / ilha_id
        
        if not ilha_dir.exists():
            return []
        
        campanhas = []
        for campanha_dir in ilha_dir.iterdir():
            if campanha_dir.is_dir():
                # Read metadata if exists
                metadata_file = campanha_dir / "metadata.json"
                if metadata_file.exists():
                    with open(metadata_file, 'r', encoding='utf-8') as f:
                        metadata = json.load(f)
                else:
                    metadata = {
                        "id": campanha_dir.name,
                        "nome": campanha_dir.name,
                        "data": "N/A"
                    }
                
                # Count files
                geospatial_dir = campanha_dir / "geospatial"
                media_dir = campanha_dir / "media"
                
                metadata["num_geospatial"] = len(list(geospatial_dir.glob("*"))) if geospatial_dir.exists() else 0
                metadata["num_media"] = len(list(media_dir.glob("*"))) if media_dir.exists() else 0
                
                campanhas.append(metadata)
        
        return campanhas
    
    def campanha_exists(self, ilha_id: str, campanha_id: str) -> bool:
        """Check if campaign exists"""
        campanha_path = self.upload_dir / ilha_id / campanha_id
        return campanha_path.exists()
    
    def get_campanha_path(self, ilha_id: str, campanha_id: str) -> Path:
        """Get campaign directory path"""
        return self.upload_dir / ilha_id / campanha_id
