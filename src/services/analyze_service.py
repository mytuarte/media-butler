"""Read-only, normalized analysis for one selected library item."""
from collections import Counter, defaultdict
from pathlib import PurePath
import ntpath
import hashlib
import re
from typing import Any
from models.media_analysis import EpisodeFileAnalysis, MovieAnalysis, SeasonAnalysis, SeriesAnalysis
from services.radarr_service import RadarrService
from services.sonarr_service import SonarrService
from services.series_progress_service import SeriesProgressService
from services.log_service import logger

def text(value: Any) -> str | None:
    """Normalize nonblank textual API values without stringifying booleans."""
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return None
def number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result >= 0 else None
def size(data: dict) -> int | None:
    for key in ("size", "sizeBytes", "length"):
        result = number(data.get(key))
        if result is not None:
            return int(result)
    return None
def quality(d):
 q=d.get('quality'); nested=q.get('quality') if isinstance(q,dict) else None
 return text(q) if isinstance(q,str) else (text(q.get('name')) if isinstance(q,dict) else None) or (text(nested.get('name')) if isinstance(nested,dict) else None) or text(d.get('qualityName'))
def resolution(v):
 """Return a concise label for known vertical resolutions without guessing."""
 value = text(v)
 if not value:
  return None
 normalized = value.lower()
 if re.fullmatch(r"\d+\s*p", normalized):
  height = int(re.sub(r"\s*p$", "", normalized))
 elif re.fullmatch(r"\d+(?:\.0+)?", normalized):
  height = int(float(normalized))
 else:
  match = re.fullmatch(r"\d+\s*[xX]\s*(\d+)", value)
  if not match:
   return value
  height = int(match.group(1))
 for target, tolerance in ((4320, 20), (2160, 20), (1440, 20), (1080, 30), (720, 20), (576, 15), (480, 15)):
  if abs(height - target) <= tolerance:
   return f"{target}p"
 return value
def codec(v):
 v=text(v); x=v.lower().replace('.','') if v else ''
 return 'HEVC' if x in ('hevc','h265','x265') else ('H.264' if x in ('avc','h264','x264') else v)
def field(d,*ks):
 for k in ks:
  if (v:=text(d.get(k))): return v
LANGUAGE_NAMES = {
 'eng': 'English', 'en': 'English', 'english': 'English',
 'ger': 'German', 'deu': 'German', 'de': 'German', 'german': 'German',
 'spa': 'Spanish', 'es': 'Spanish', 'spanish': 'Spanish',
 'fre': 'French', 'fra': 'French', 'fr': 'French', 'french': 'French',
 'ita': 'Italian', 'it': 'Italian', 'italian': 'Italian',
 'jpn': 'Japanese', 'ja': 'Japanese', 'japanese': 'Japanese',
 'kor': 'Korean', 'ko': 'Korean', 'korean': 'Korean',
 'chi': 'Chinese', 'zho': 'Chinese', 'zh': 'Chinese', 'chinese': 'Chinese',
 'por': 'Portuguese', 'pt': 'Portuguese', 'portuguese': 'Portuguese',
 'rus': 'Russian', 'ru': 'Russian', 'russian': 'Russian',
}
def languages(v):
 """Normalize Radarr/Sonarr language forms into sorted readable names."""
 items = v if isinstance(v, list) else [v]
 values = []
 for item in items:
  raw = text(item.get('name')) if isinstance(item, dict) else text(item)
  if raw:
   values.extend(part.strip() for part in re.split(r'[/,]', raw) if part.strip())
 normalized = {LANGUAGE_NAMES.get(value.casefold(), value) for value in values}
 return sorted(normalized, key=lambda value: (value.casefold(), value))
def channels(v):
 if isinstance(v,bool):return None
 if isinstance(v,(int,float)): return {2:'2.0',6:'5.1',8:'7.1'}.get(v)
 return text(v)
def normalized_identifier(value: Any) -> str | None:
    """Make numeric and string Sonarr identifiers comparable."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        return str(int(value))
    except (TypeError, ValueError):
        return text(value)


def safe_relative_path(value: Any) -> str | None:
    """Keep relative paths but reduce POSIX, drive, and UNC paths to a filename."""
    path = text(value)
    if not path:
        return None
    windows_absolute = path.startswith("\\") or (len(path) > 2 and path[1] == ":")
    if PurePath(path).is_absolute() or windows_absolute:
        return ntpath.basename(path) or PurePath(path).name or None
    return path


def distinct_release(filename: Any, release: Any) -> str | None:
    """Return a safe release label only when it differs from the filename."""
    safe_release = safe_relative_path(release)
    if not safe_release:
        return None
    safe_filename = safe_relative_path(filename)
    if not safe_filename:
        return safe_release
    def comparable(value: str) -> str:
        basename = ntpath.basename(value.replace('/', '\\'))
        stem, extension = ntpath.splitext(basename)
        if extension.casefold() in {'.mkv', '.mp4', '.avi', '.mov', '.m4v', '.ts', '.webm', '.wmv'}:
            basename = stem
        return basename.casefold()
    return None if comparable(safe_filename) == comparable(safe_release) else safe_release


def physical_file_key(file: dict, normalized: dict) -> str:
    path = normalized["path"]
    if path:
        return f"path:{path.lower()}"
    identifier = normalized_identifier(file.get("id"))
    if identifier:
        return f"id:{identifier}"
    signature = "|".join(str(normalized.get(key) or "") for key in ("size", "quality", "resolution", "video_codec", "audio_codec"))
    return "metadata:" + hashlib.sha256(signature.encode()).hexdigest()[:16]

def fields(f):
 info=f.get('mediaInfo') if isinstance(f.get('mediaInfo'),dict) else {}; q=f.get('quality'); nq=q.get('quality') if isinstance(q,dict) and isinstance(q.get('quality'),dict) else {}
 path=safe_relative_path(field(f, 'relativePath', 'fileName'))
 release=distinct_release(path, field(f,'sceneName','releaseTitle'))
 return dict(size=size(f),quality=quality(f),resolution=resolution(field(info,'resolution','videoResolution') or field(f,'resolution') or text(nq.get('resolution'))),video_codec=codec(field(info,'videoCodec','videoFormat')),dynamic_range=field(info,'videoDynamicRange','videoDynamicRangeType','dynamicRange','hdrFormat'),audio_codec=field(info,'audioCodec','audioFormat'),audio_channels=channels(info.get('audioChannels',info.get('audioChannelPositions'))),audio_languages=languages(info.get('audioLanguages') or info.get('audioLanguage') or f.get('languages')),path=path,release=release)
def dist(entries,attr): return dict(sorted(Counter(getattr(x,attr) for x in entries if getattr(x,attr)).items(),key=lambda x:(-x[1],x[0])))
def sums(entries):
 known=[x.size_bytes for x in entries if x.size_bytes is not None]; return (sum(known) if known else None,len(known),len(entries)-len(known),sum(known)/len(known) if known else None)
class AnalyzeService:
 def __init__(self,radarr=None,sonarr=None,progress_service=None): self.radarr=radarr or RadarrService();self.sonarr=sonarr or SonarrService();self.progress=progress_service or SeriesProgressService(self.sonarr)
 def analyze(self,m): return self.analyze_series(m) if m.media_type=='series' else self.analyze_movie(m)
 def analyze_movie(self,m):
  r=self.radarr.get_movie_by_id(m.id)
  if r is None: raise ValueError('Movie unavailable')
  runtime=number(r.get('runtime')); f=r.get('movieFile') if isinstance(r.get('movieFile'),dict) else None
  if not f:return MovieAnalysis('movie',m.title,m.year,None,0,warnings=['No movie file exists.'],runtime_minutes=runtime)
  x=fields(f); known=int(x['size'] is not None); rate=x['size']/(runtime/60) if x['size'] is not None and runtime and runtime>0 else None; bitrate=x['size']*8/(runtime*60)/1e6 if rate is not None else None
  return MovieAnalysis('movie',m.title,m.year,x['size'],1,known,1-known,dist([type('X',(),x)()], 'quality'),dist([type('X',(),x)()], 'resolution'),dist([type('X',(),x)()], 'video_codec'),dist([type('X',(),x)()], 'audio_codec'),runtime_minutes=runtime,size_bytes=x['size'],size_per_hour_bytes=rate,estimated_total_bitrate_mbps=bitrate,quality=x['quality'],resolution=x['resolution'],video_codec=x['video_codec'],video_dynamic_range=x['dynamic_range'],audio_codec=x['audio_codec'],audio_channels=x['audio_channels'],audio_languages=x['audio_languages'],file_relative_path=x['path'],original_release_name=x['release'])
 def analyze_series(self,m):
  if not isinstance(self.sonarr.get_series_by_id(m.id),dict):raise ValueError('Series unavailable')
  eps=self.sonarr.get_episodes(m.id,refresh=True); files=self.sonarr.get_episode_files(m.id); byfile=defaultdict(list); byid={}
  for e in eps if isinstance(eps,list) else []:
   if isinstance(e,dict):
    if normalized_identifier(e.get('episodeFileId')) is not None:
     byfile[normalized_identifier(e.get('episodeFileId'))].append(e)
    if normalized_identifier(e.get('id')) is not None:
     byid[normalized_identifier(e.get('id'))] = e
  entries=[]
  for f in files if isinstance(files,list) else []:
   if not isinstance(f,dict):continue
   associated = byfile.get(normalized_identifier(f.get('id')), [])
   direct = byid.get(normalized_identifier(f.get('episodeId')))
   if direct is not None and direct not in associated:
    associated.append(direct)
   associated.sort(key=lambda item: (int(item.get('seasonNumber', 10**9)), int(item.get('episodeNumber', 10**9)), normalized_identifier(item.get('id')) or ''))
   e = associated[0] if associated else None
   if not isinstance(e,dict): logger.warning('Unmatched Sonarr episode file id=%r',f.get('id')); season=episode=None; title=None
   else:
    try: season=int(e['seasonNumber']);episode=int(e['episodeNumber']);title=text(e.get('title'))
    except (KeyError,TypeError,ValueError): logger.warning('Malformed Sonarr episode metadata for file id=%r',f.get('id'));season=episode=None;title=None
   x=fields(f);entries.append(EpisodeFileAnalysis(season,episode,title,x['size'],x['quality'],x['resolution'],x['video_codec'],x['audio_codec'],x['audio_channels'],x['path'], physical_file_key(f, x)))
  total,k,u,avg=sums(entries); groups=defaultdict(list)
  for e in entries:
   if e.season_number is not None:groups[e.season_number].append(e)
  seasons=[]
  for n,items in groups.items():
   t,kk,uu,a=sums(items);seasons.append(SeasonAnalysis(n,len(items),t,a,kk,uu,dist(items,'quality'),dist(items,'resolution'),dist(items,'video_codec')))
  p=self.progress.evaluate(m.id);special=groups.get(0,[]); st,_,_,_=sums(special); warns=[f'{u} file sizes unavailable.'] if u else []
  return SeriesAnalysis('series',m.title,m.year,total,len(entries),k,u,dist(entries,'quality'),dist(entries,'resolution'),dist(entries,'video_codec'),dist(entries,'audio_codec'),warns,m.id,len(entries),avg,sorted(seasons,key=lambda x:x.season_number),sorted(entries,key=lambda x:(-(x.size_bytes if x.size_bytes is not None else -1),x.season_number is None,x.season_number or 0,x.episode_number or 0,x.physical_file_key))[:5],p.released_count,p.imported_released_count,len(special),st)
