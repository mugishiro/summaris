import 'server-only';

type SourceMetadata = {
  id: string;
  name: string;
  url: string;
  feedUrl?: string;
  defaultTopics: string[];
};

const SOURCE_CATALOG: Record<string, SourceMetadata> = {
  'nhk-news': {
    id: 'nhk-news',
    name: 'NHK News',
    url: 'https://www3.nhk.or.jp/news/',
    feedUrl: 'https://www3.nhk.or.jp/rss/news/cat0.xml',
    defaultTopics: ['国内', '社会'],
  },
  'bbc-world': {
    id: 'bbc-world',
    name: 'BBC World News',
    url: 'https://www.bbc.com/news/world',
    feedUrl: 'https://feeds.bbci.co.uk/news/world/rss.xml',
    defaultTopics: ['国際', '世界'],
  },
  'al-jazeera-english': {
    id: 'al-jazeera-english',
    name: 'Al Jazeera English',
    url: 'https://www.aljazeera.com/',
    feedUrl: 'https://www.aljazeera.com/xml/rss/all.xml',
    defaultTopics: ['国際', '中東'],
  },
  'dw-world': {
    id: 'dw-world',
    name: 'Deutsche Welle World',
    url: 'https://www.dw.com/en/world',
    feedUrl: 'https://rss.dw.com/rdf/rss-en-world',
    defaultTopics: ['国際', 'ヨーロッパ'],
  },
  'el-pais': {
    id: 'el-pais',
    name: 'EL PAÍS',
    url: 'https://elpais.com/',
    feedUrl: 'https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/portada',
    defaultTopics: ['国際', 'スペイン'],
  },
  'straits-times': {
    id: 'straits-times',
    name: 'The Straits Times',
    url: 'https://www.straitstimes.com/news/world',
    feedUrl: 'https://www.straitstimes.com/news/world/rss.xml',
    defaultTopics: ['国際', 'アジア'],
  },
  'times-of-india': {
    id: 'times-of-india',
    name: 'The Times of India',
    url: 'https://timesofindia.indiatimes.com/',
    feedUrl: 'https://timesofindia.indiatimes.com/rssfeedstopstories.cms',
    defaultTopics: ['国際', 'インド'],
  },
  'allafrica-latest': {
    id: 'allafrica-latest',
    name: 'AllAfrica Latest',
    url: 'https://allafrica.com/latest/',
    feedUrl: 'https://allafrica.com/tools/headlines/rdf/latest/headlines.rdf',
    defaultTopics: ['国際', 'アフリカ'],
  },
};

export function getSourceMetadata(sourceId: string) {
  const meta = SOURCE_CATALOG[sourceId];
  if (meta) {
    return meta;
  }
  return {
    id: sourceId,
    name: sourceId.replace(/[-_]/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase()),
    url: '',
    feedUrl: undefined,
    defaultTopics: ['general'],
  };
}
