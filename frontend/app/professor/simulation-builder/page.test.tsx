
// ============================================================================
// Unit Tests for Utility Functions
// ============================================================================

describe('normalizeScenes', () => {
  it('should preserve image_url when present', () => {
    const scenes = [
      { id: 1, name: 'Scene 1', image_url: 'https://example.com/image.jpg', timeout_turns: 10 }
    ];
    const result = normalizeScenes(scenes);
    expect(result[0].image_url).toBe('https://example.com/image.jpg');
  });

  it('should set timeout_turns to 15 when undefined', () => {
    const scenes = [
      { id: 1, name: 'Scene 1', image_url: 'https://example.com/image.jpg' }
    ];
    const result = normalizeScenes(scenes);
    expect(result[0].timeout_turns).toBe(15);
  });

  it('should set timeout_turns to 15 when null', () => {
    const scenes = [
      { id: 1, name: 'Scene 1', image_url: 'https://example.com/image.jpg', timeout_turns: null }
    ];
    const result = normalizeScenes(scenes);
    expect(result[0].timeout_turns).toBe(15);
  });

  it('should preserve timeout_turns when explicitly set to 0', () => {
    const scenes = [
      { id: 1, name: 'Scene 1', image_url: 'https://example.com/image.jpg', timeout_turns: 0 }
    ];
    const result = normalizeScenes(scenes);
    expect(result[0].timeout_turns).toBe(0);
  });

  it('should preserve existing timeout_turns value', () => {
    const scenes = [
      { id: 1, name: 'Scene 1', image_url: 'https://example.com/image.jpg', timeout_turns: 25 }
    ];
    const result = normalizeScenes(scenes);
    expect(result[0].timeout_turns).toBe(25);
  });

  it('should handle multiple scenes correctly', () => {
    const scenes = [
      { id: 1, name: 'Scene 1', image_url: 'img1.jpg', timeout_turns: 5 },
      { id: 2, name: 'Scene 2', image_url: 'img2.jpg' },
      { id: 3, name: 'Scene 3', image_url: 'img3.jpg', timeout_turns: null }
    ];
    const result = normalizeScenes(scenes);
    expect(result[0].timeout_turns).toBe(5);
    expect(result[1].timeout_turns).toBe(15);
    expect(result[2].timeout_turns).toBe(15);
  });

  it('should handle empty array', () => {
    const scenes: any[] = [];
    const result = normalizeScenes(scenes);
    expect(result).toEqual([]);
  });

  it('should preserve all other scene properties', () => {
    const scenes = [
      { 
        id: 1, 
        name: 'Scene 1', 
        description: 'Test scene',
        image_url: 'https://example.com/image.jpg',
        custom_prop: 'custom_value',
        timeout_turns: 10 
      }
    ];
    const result = normalizeScenes(scenes);
    expect(result[0].id).toBe(1);
    expect(result[0].name).toBe('Scene 1');
    expect(result[0].description).toBe('Test scene');
    expect(result[0].custom_prop).toBe('custom_value');
  });
});

describe('extractPlayerName', () => {
  it('should extract name before "at"', () => {
    const result = extractPlayerName('Greg James at Sun Microsystems');
    expect(result).toBe('Greg James');
  });

  it('should extract name before "in"', () => {
    const result = extractPlayerName('John Smith in Technology Division');
    expect(result).toBe('John Smith');
  });

  it('should extract name before comma', () => {
    const result = extractPlayerName('Alice Johnson, CEO');
    expect(result).toBe('Alice Johnson');
  });

  it('should extract name before hyphen', () => {
    const result = extractPlayerName('Bob Williams - Senior Developer');
    expect(result).toBe('Bob Williams');
  });

  it('should return trimmed title if no delimiter found', () => {
    const result = extractPlayerName('Sarah Connor');
    expect(result).toBe('Sarah Connor');
  });

  it('should return empty string for empty input', () => {
    const result = extractPlayerName('');
    expect(result).toBe('');
  });

  it('should return empty string for null input', () => {
    const result = extractPlayerName(null as any);
    expect(result).toBe('');
  });

  it('should return empty string for undefined input', () => {
    const result = extractPlayerName(undefined as any);
    expect(result).toBe('');
  });

  it('should handle titles with multiple delimiters', () => {
    const result = extractPlayerName('Mike Davis at Google, Engineering Lead');
    expect(result).toBe('Mike Davis');
  });

  it('should trim whitespace from extracted name', () => {
    const result = extractPlayerName('  Jane Doe  at Company');
    expect(result).toBe('Jane Doe');
  });

  it('should handle case-insensitive matching', () => {
    const result = extractPlayerName('Tom Brown AT Microsoft');
    expect(result).toBe('Tom Brown');
  });

  it('should handle title ending immediately after name', () => {
    const result = extractPlayerName('Emma Wilson at');
    expect(result).toBe('Emma Wilson');
  });
});

describe('normalizeName', () => {
  it('should convert to lowercase', () => {
    const result = normalizeName('John Smith');
    expect(result).toBe('john smith');
  });

  it('should remove special characters', () => {
    const result = normalizeName('John-Paul Smith\!');
    expect(result).toBe('johnpaul smith');
  });

  it('should remove numbers', () => {
    const result = normalizeName('John Smith 123');
    expect(result).toBe('john smith ');
  });

  it('should trim whitespace', () => {
    const result = normalizeName('  John Smith  ');
    expect(result).toBe('john smith');
  });

  it('should handle empty string', () => {
    const result = normalizeName('');
    expect(result).toBe('');
  });

  it('should handle null input', () => {
    const result = normalizeName(null as any);
    expect(result).toBe('');
  });

  it('should handle undefined input', () => {
    const result = normalizeName(undefined as any);
    expect(result).toBe('');
  });

  it('should preserve spaces between words', () => {
    const result = normalizeName('Mary Jane Watson');
    expect(result).toBe('mary jane watson');
  });

  it('should remove all punctuation', () => {
    const result = normalizeName("O'Connor-Smith, Jr.");
    expect(result).toBe('oconnorsmith jr');
  });

  it('should handle names with only special characters', () => {
    const result = normalizeName('\!@#$%^&*()');
    expect(result).toBe('');
  });
});

describe('isLikelySamePerson', () => {
  it('should return true for exact match after normalization', () => {
    const result = isLikelySamePerson('John Smith', 'john smith');
    expect(result).toBe(true);
  });

  it('should return true when first and last name match', () => {
    const result = isLikelySamePerson('John Michael Smith', 'John Smith');
    expect(result).toBe(true);
  });

  it('should return false for empty inputs', () => {
    expect(isLikelySamePerson('', '')).toBe(false);
    expect(isLikelySamePerson('John', '')).toBe(false);
    expect(isLikelySamePerson('', 'Smith')).toBe(false);
  });

  it('should return false for null inputs', () => {
    expect(isLikelySamePerson(null as any, null as any)).toBe(false);
    expect(isLikelySamePerson('John Smith', null as any)).toBe(false);
  });

  it('should return false when only one word matches', () => {
    const result = isLikelySamePerson('John Smith', 'John Doe');
    expect(result).toBe(false);
  });

  it('should return true when two or more words overlap', () => {
    const result = isLikelySamePerson('John Michael Smith', 'Michael Smith Johnson');
    expect(result).toBe(true);
  });

  it('should handle special characters in names', () => {
    const result = isLikelySamePerson('Mary-Jane Watson', 'Mary Jane Watson');
    expect(result).toBe(true);
  });

  it('should be case insensitive', () => {
    const result = isLikelySamePerson('JOHN SMITH', 'john smith');
    expect(result).toBe(true);
  });

  it('should return false for completely different names', () => {
    const result = isLikelySamePerson('Alice Johnson', 'Bob Williams');
    expect(result).toBe(false);
  });

  it('should handle single-word names', () => {
    const result = isLikelySamePerson('Madonna', 'Cher');
    expect(result).toBe(false);
  });

  it('should return true for names with different middle names but same first and last', () => {
    const result = isLikelySamePerson('John Paul Smith', 'John Michael Smith');
    expect(result).toBe(true);
  });

  it('should handle names with extra whitespace', () => {
    const result = isLikelySamePerson('John  Smith', 'John Smith');
    expect(result).toBe(true);
  });
});

describe('formatDescription', () => {
  it('should return empty string for empty input', () => {
    const result = formatDescription('');
    expect(result).toBe('');
  });

  it('should return empty string for null input', () => {
    const result = formatDescription(null as any);
    expect(result).toBe('');
  });

  it('should clean up excessive whitespace', () => {
    const result = formatDescription('This  is   a    test.');
    expect(result).toBe('This is a test.');
  });

  it('should split by double line breaks', () => {
    const result = formatDescription('First paragraph.\n\nSecond paragraph.');
    expect(result).toBe('First paragraph.\n\nSecond paragraph.');
  });

  it('should split by single line breaks when no double breaks exist', () => {
    const result = formatDescription('First paragraph.\nSecond paragraph.');
    expect(result).toBe('First paragraph.\n\nSecond paragraph.');
  });

  it('should group sentences into paragraphs when no line breaks exist', () => {
    const result = formatDescription('First sentence. Second sentence. Third sentence. Fourth sentence.');
    expect(result).toContain('First sentence. Second sentence.');
  });

  it('should add period to paragraphs without proper ending', () => {
    const result = formatDescription('This is a test paragraph');
    expect(result).toBe('This is a test paragraph.');
  });

  it('should preserve existing periods', () => {
    const result = formatDescription('This is a test.');
    expect(result).toBe('This is a test.');
  });

  it('should preserve exclamation marks', () => {
    const result = formatDescription('This is exciting\!');
    expect(result).toBe('This is exciting\!');
  });

  it('should preserve question marks', () => {
    const result = formatDescription('Is this a test?');
    expect(result).toBe('Is this a test?');
  });

  it('should filter out empty paragraphs', () => {
    const result = formatDescription('First paragraph.\n\n\n\nSecond paragraph.');
    expect(result).toBe('First paragraph.\n\nSecond paragraph.');
  });

  it('should handle text with only whitespace', () => {
    const result = formatDescription('   \n\n   ');
    expect(result).toBe('');
  });

  it('should join multiple paragraphs with double line breaks', () => {
    const input = 'Para one.\nPara two.\nPara three.';
    const result = formatDescription(input);
    expect(result).toContain('\n\n');
  });

  it('should handle complex multi-paragraph text', () => {
    const input = 'This is the first paragraph.\n\nThis is the second paragraph.\n\nThis is the third paragraph.';
    const result = formatDescription(input);
    const paragraphs = result.split('\n\n');
    expect(paragraphs).toHaveLength(3);
  });

  it('should trim each paragraph', () => {
    const result = formatDescription('  First paragraph  \n\n  Second paragraph  ');
    expect(result).toBe('First paragraph.\n\nSecond paragraph.');
  });

  it('should handle sentences with multiple punctuation types', () => {
    const result = formatDescription('Hello\! How are you? I am fine.');
    expect(result).toMatch(/^Hello\! How are you?/);
  });
});

describe('formatLearningOutcomes', () => {
  it('should return empty string for null input', () => {
    const result = formatLearningOutcomes(null as any);
    expect(result).toBe('');
  });

  it('should return empty string for undefined input', () => {
    const result = formatLearningOutcomes(undefined as any);
    expect(result).toBe('');
  });

  it('should return empty string for empty array', () => {
    const result = formatLearningOutcomes([]);
    expect(result).toBe('');
  });

  it('should add proper numbering', () => {
    const outcomes = ['learn something', 'understand concepts'];
    const result = formatLearningOutcomes(outcomes);
    expect(result).toContain('1. Learn something.');
    expect(result).toContain('2. Understand concepts.');
  });

  it('should remove existing numbering', () => {
    const outcomes = ['1. Learn something', '2. Understand concepts'];
    const result = formatLearningOutcomes(outcomes);
    expect(result).toContain('1. Learn something.');
    expect(result).toContain('2. Understand concepts.');
  });

  it('should remove bullet points', () => {
    const outcomes = ['• Learn something', '• Understand concepts'];
    const result = formatLearningOutcomes(outcomes);
    expect(result).toContain('1. Learn something.');
  });

  it('should remove asterisk bullets', () => {
    const outcomes = ['* Learn something', '* Understand concepts'];
    const result = formatLearningOutcomes(outcomes);
    expect(result).toContain('1. Learn something.');
  });

  it('should remove hyphen bullets', () => {
    const outcomes = ['- Learn something', '- Understand concepts'];
    const result = formatLearningOutcomes(outcomes);
    expect(result).toContain('1. Learn something.');
  });

  it('should capitalize first letter', () => {
    const outcomes = ['learn something'];
    const result = formatLearningOutcomes(outcomes);
    expect(result).toContain('1. Learn something.');
  });

  it('should not double-capitalize', () => {
    const outcomes = ['Learn something'];
    const result = formatLearningOutcomes(outcomes);
    expect(result).toContain('1. Learn something.');
  });

  it('should add period if missing', () => {
    const outcomes = ['Learn something'];
    const result = formatLearningOutcomes(outcomes);
    expect(result).toContain('Learn something.');
  });

  it('should preserve existing period', () => {
    const outcomes = ['Learn something.'];
    const result = formatLearningOutcomes(outcomes);
    expect(result).toContain('1. Learn something.');
  });

  it('should preserve exclamation marks', () => {
    const outcomes = ['Master this skill\!'];
    const result = formatLearningOutcomes(outcomes);
    expect(result).toContain('Master this skill\!');
  });

  it('should preserve question marks', () => {
    const outcomes = ['Can you solve this?'];
    const result = formatLearningOutcomes(outcomes);
    expect(result).toContain('Can you solve this?');
  });

  it('should join with double line breaks', () => {
    const outcomes = ['First outcome', 'Second outcome'];
    const result = formatLearningOutcomes(outcomes);
    expect(result).toContain('\n\n');
  });

  it('should filter out empty outcomes', () => {
    const outcomes = ['Learn something', '', 'Understand concepts'];
    const result = formatLearningOutcomes(outcomes);
    expect(result.split('\n\n')).toHaveLength(2);
  });

  it('should handle whitespace-only outcomes', () => {
    const outcomes = ['Learn something', '   ', 'Understand concepts'];
    const result = formatLearningOutcomes(outcomes);
    const lines = result.split('\n\n').filter(line => line.trim());
    expect(lines).toHaveLength(2);
  });

  it('should handle mixed formatting in input', () => {
    const outcomes = [
      '1. learn first thing',
      '• understand second thing',
      '- master third skill\!',
      'accomplish fourth goal'
    ];
    const result = formatLearningOutcomes(outcomes);
    expect(result).toContain('1. Learn first thing.');
    expect(result).toContain('2. Understand second thing.');
    expect(result).toContain('3. Master third skill\!');
    expect(result).toContain('4. Accomplish fourth goal.');
  });

  it('should trim whitespace from each outcome', () => {
    const outcomes = ['  Learn something  ', '  Understand concepts  '];
    const result = formatLearningOutcomes(outcomes);
    expect(result).toContain('1. Learn something.');
  });
});

describe('extractSingleNames', () => {
  it('should extract capitalized names from title', () => {
    const result = extractSingleNames('Greg James at Company', '');
    expect(result).toContain('Greg');
    expect(result).toContain('James');
  });

  it('should extract capitalized names from description', () => {
    const result = extractSingleNames('', 'Alice works with Bob');
    expect(result).toContain('Alice');
    expect(result).toContain('Bob');
  });

  it('should extract names from both title and description', () => {
    const result = extractSingleNames('Greg at Company', 'Alice is the manager');
    expect(result).toContain('Greg');
    expect(result).toContain('Alice');
  });

  it('should filter out common words', () => {
    const result = extractSingleNames('The Company Network', '');
    expect(result).not.toContain('The');
    expect(result).not.toContain('Company');
    expect(result).not.toContain('Network');
  });

  it('should not include duplicate names', () => {
    const result = extractSingleNames('John works with John', '');
    expect(result.filter(name => name === 'John')).toHaveLength(1);
  });

  it('should require names to be at least 3 characters', () => {
    const result = extractSingleNames('Al and Bob work together', '');
    expect(result).not.toContain('Al');
    expect(result).toContain('Bob');
  });

  it('should extract names that start with capital letter', () => {
    const result = extractSingleNames('Sarah and mike work together', '');
    expect(result).toContain('Sarah');
    expect(result).not.toContain('mike');
  });

  it('should handle empty inputs', () => {
    const result = extractSingleNames('', '');
    expect(result).toEqual([]);
  });

  it('should handle text with no capitalized names', () => {
    const result = extractSingleNames('the company network', 'working with others');
    expect(result).toEqual([]);
  });

  it('should filter out "Ltd"', () => {
    const result = extractSingleNames('Microsoft Ltd', '');
    expect(result).not.toContain('Ltd');
  });

  it('should filter out "Inc"', () => {
    const result = extractSingleNames('Apple Inc', '');
    expect(result).not.toContain('Inc');
  });

  it('should filter out "Corp"', () => {
    const result = extractSingleNames('Google Corp', '');
    expect(result).not.toContain('Corp');
  });

  it('should extract multiple unique names', () => {
    const result = extractSingleNames('Alice, Bob, and Charlie', 'David works here');
    expect(result).toContain('Alice');
    expect(result).toContain('Bob');
    expect(result).toContain('Charlie');
    expect(result).toContain('David');
  });

  it('should handle names with apostrophes in context', () => {
    const result = extractSingleNames("John's company", '');
    expect(result).toContain('John');
  });

  it('should handle camelCase as single capitalized word', () => {
    const result = extractSingleNames('TechCorp has employees', '');
    expect(result).toContain('TechCorp');
  });

  it('should preserve order of first occurrence', () => {
    const result = extractSingleNames('Alice meets Bob', '');
    expect(result.indexOf('Alice')).toBeLessThan(result.indexOf('Bob'));
  });

  it('should handle punctuation around names', () => {
    const result = extractSingleNames('(Alice) and [Bob]', '');
    expect(result).toContain('Alice');
    expect(result).toContain('Bob');
  });
});