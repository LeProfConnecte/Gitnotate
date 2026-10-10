#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitNotate - Nettoyeur de Doublons dans PAGE SOURCE v1.0
Supprime les URLs GitHub en doublon dans la page Notion source
"""

import requests
import os
import time
import re
from pathlib import Path
from dotenv import load_dotenv
from typing import Dict, List, Set

# --- CONFIGURATION ---
current_dir = Path(__file__).resolve().parent
env_path = current_dir / '.env'

print(f"📂 Dossier : {current_dir}")
print(f"📄 Fichier .env : {env_path}")

if env_path.exists():
    load_dotenv(dotenv_path=env_path)
    print("✅ .env chargé\n")
else:
    print("❌ .env non trouvé\n")
    load_dotenv()

NOTION_TOKEN = os.environ.get('NOTION_TOKEN', '').strip()
PARENT_PAGE_ID = os.environ.get('PARENT_PAGE_ID', '').strip()
DRY_RUN = str(os.environ.get('DRY_RUN', 'false')).lower() == 'true'

NOTION_HEADERS = {
    'Authorization': f'Bearer {NOTION_TOKEN}',
    'Content-Type': 'application/json',
    'Notion-Version': '2022-06-28'
}


def normalize_github_url(url: str) -> str:
    """Normalise une URL GitHub pour comparaison"""
    url = url.lower().strip().rstrip('/')
    url = url.replace('http://', 'https://')
    url = re.sub(r'\.git$', '', url, flags=re.IGNORECASE)
    return url


def get_all_blocks_recursive(block_id: str, blocks: List = None, depth: int = 0, max_depth: int = 50) -> List[Dict]:
    """Récupère tous les blocs d'une page récursivement"""
    if blocks is None:
        blocks = []
    if depth >= max_depth:
        return blocks

    url = f'https://api.notion.com/v1/blocks/{block_id}/children'
    start_cursor = None

    while True:
        params = {'page_size': 100}
        if start_cursor:
            params['start_cursor'] = start_cursor

        response = requests.get(url, headers=NOTION_HEADERS, params=params, timeout=30)

        if not response or response.status_code not in (200, 201):
            break

        data = response.json()
        results = data.get('results', [])

        for block in results:
            blocks.append(block)
            if block.get('has_children', False):
                get_all_blocks_recursive(block['id'], blocks, depth + 1, max_depth)

        if not data.get('has_more', False):
            break

        start_cursor = data.get('next_cursor')
        if not start_cursor:
            break

    return blocks


def extract_github_urls_from_blocks(blocks: List[Dict]) -> List[Dict]:
    """
    Extrait les URLs GitHub avec leur block_id pour suppression
    Retourne: [{'url': 'https://...', 'block_id': '...', 'block_type': '...'}, ...]
    """
    github_blocks = []

    for block in blocks:
        block_type = block.get('type')
        block_id = block['id']

        # Cas 1: Bookmark
        if block_type == 'bookmark':
            url = block.get('bookmark', {}).get('url', '')
            if 'github.com' in url:
                github_blocks.append({
                    'url': url,
                    'block_id': block_id,
                    'block_type': 'bookmark',
                    'normalized': normalize_github_url(url)
                })

        # Cas 2: Link Preview
        elif block_type == 'link_preview':
            url = block.get('link_preview', {}).get('url', '')
            if 'github.com' in url:
                github_blocks.append({
                    'url': url,
                    'block_id': block_id,
                    'block_type': 'link_preview',
                    'normalized': normalize_github_url(url)
                })

        # Cas 3: Embed
        elif block_type == 'embed':
            url = block.get('embed', {}).get('url', '')
            if 'github.com' in url:
                github_blocks.append({
                    'url': url,
                    'block_id': block_id,
                    'block_type': 'embed',
                    'normalized': normalize_github_url(url)
                })

        # Cas 4: Texte (paragraphe, liste, etc.)
        elif block_type in ['paragraph', 'heading_1', 'heading_2', 'heading_3',
                            'bulleted_list_item', 'numbered_list_item']:
            rich_text = block.get(block_type, {}).get('rich_text', [])

            for text_obj in rich_text:
                # URL dans un lien
                link = text_obj.get('text', {}).get('link')
                if link:
                    url = link.get('url', '')
                    if 'github.com' in url:
                        github_blocks.append({
                            'url': url,
                            'block_id': block_id,
                            'block_type': f'{block_type}_link',
                            'normalized': normalize_github_url(url),
                            'text_block': True  # On ne peut pas supprimer juste le lien
                        })

                # URL dans le texte brut
                content = text_obj.get('text', {}).get('content', '')
                urls = re.findall(r'https?://(?:www\.)?github\.com[^\s\)]+', content)
                for url in urls:
                    github_blocks.append({
                        'url': url,
                        'block_id': block_id,
                        'block_type': f'{block_type}_text',
                        'normalized': normalize_github_url(url),
                        'text_block': True
                    })

    return github_blocks


def detect_and_remove_duplicates(page_id: str, dry_run: bool = False):
    """Détecte et supprime les doublons dans la page"""
    print("=" * 70)
    print("🧹 NETTOYEUR DE DOUBLONS - PAGE SOURCE NOTION")
    print("=" * 70)
    print()

    if not NOTION_TOKEN:
        print("❌ NOTION_TOKEN manquant")
        return

    if not page_id:
        print("❌ PARENT_PAGE_ID manquant")
        return

    print(f"🔑 Token : {NOTION_TOKEN[:4]}...{NOTION_TOKEN[-4:]}")
    print(f"📄 Page ID : {page_id}")

    if dry_run:
        print("\n🔍 MODE DRY-RUN : Simulation (aucune suppression)")

    # Récupérer tous les blocs
    print("\n📥 Récupération des blocs de la page...")
    blocks = get_all_blocks_recursive(page_id)
    print(f"✅ {len(blocks)} blocs récupérés")

    # Extraire les URLs GitHub
    print("\n🔍 Extraction des URLs GitHub...")
    github_blocks = extract_github_urls_from_blocks(blocks)
    print(f"✅ {len(github_blocks)} URLs GitHub trouvées")

    if not github_blocks:
        print("\n✅ Aucune URL GitHub trouvée")
        return

    # Détecter les doublons
    print("\n🔍 Détection des doublons...")
    seen = {}  # {url_normalized: [blocks...]}

    for block_info in github_blocks:
        norm_url = block_info['normalized']
        if norm_url not in seen:
            seen[norm_url] = []
        seen[norm_url].append(block_info)

    # Identifier les doublons
    duplicates_to_delete = []
    unique_count = 0

    for norm_url, block_list in seen.items():
        if len(block_list) > 1:
            # Garder le premier, supprimer les autres
            keep = block_list[0]
            delete = block_list[1:]

            print(f"\n⚠️  URL : {block_list[0]['url']}")
            print(f"  📌 GARDE : Block {keep['block_id']} ({keep['block_type']})")
            print(f"  🗑️  SUPPRIME : {len(delete)} bloc(s)")

            for dup in delete:
                # Ne supprimer que les blocs entiers (pas les liens dans du texte)
                if not dup.get('text_block', False):
                    duplicates_to_delete.append(dup)
                else:
                    print(f"      ⚠️ Skip {dup['block_id']} (lien dans texte, suppression manuelle requise)")
        else:
            unique_count += 1

    print(f"\n📊 Bilan :")
    print(f"  • URLs uniques : {unique_count}")
    print(f"  • URLs en doublon : {len(seen) - unique_count}")
    print(f"  • Blocs à supprimer : {len(duplicates_to_delete)}")

    if not duplicates_to_delete:
        print("\n✅ Aucun doublon supprimable (ou tous sont dans du texte)")
        return

    if dry_run:
        print("\n🔍 MODE DRY-RUN : Aucune suppression effectuée")
        print("💡 Pour supprimer : DRY_RUN=false python clean_page_duplicates.py")
        return

    # Confirmation
    try:
        response = input(f"\n❓ Confirmer la suppression de {len(duplicates_to_delete)} blocs ? (OUI/non) : ")
        if response.strip().upper() not in ['OUI', 'Y', 'YES', 'O']:
            print("❌ Annulé")
            return
    except (EOFError, KeyboardInterrupt):
        print("\n❌ Annulé")
        return

    # Suppression
    print("\n🗑️  Suppression en cours...")
    deleted = 0

    for i, block_info in enumerate(duplicates_to_delete, 1):
        try:
            resp = requests.delete(
                f"https://api.notion.com/v1/blocks/{block_info['block_id']}",
                headers=NOTION_HEADERS,
                timeout=10
            )

            if resp.status_code == 200:
                deleted += 1
                print(f"  ✅ [{i}/{len(duplicates_to_delete)}] Supprimé : {block_info['url'][:60]}...")
            else:
                print(f"  ❌ [{i}/{len(duplicates_to_delete)}] Échec ({resp.status_code})")

            time.sleep(0.35)  # Rate limit Notion

        except Exception as e:
            print(f"  ❌ Erreur : {e}")

    print(f"\n✅ TERMINÉ : {deleted}/{len(duplicates_to_delete)} blocs supprimés")
    print("=" * 70)


if __name__ == '__main__':
    detect_and_remove_duplicates(PARENT_PAGE_ID, dry_run=DRY_RUN)
