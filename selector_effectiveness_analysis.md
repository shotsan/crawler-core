# Discovered Selector Effectiveness Analysis

## Victoria's Secret Test

### Selectors Discovered in Phase 1.5:
1. `.onetrust-banner-container` (95% cookie_framework) - **DISCOVERED**
2. `[aria-modal="true"]` (95% modal)
3. `#utag_201` (95% accept_button)
4. `[role="dialog"]` (90% modal)
5. `.onetrust` (90% cookie_script)

### What Actually Worked:
- ✅ Used: `#onetrust-banner-sdk` - **NOT DISCOVERED, added by OneTrust-specific handler**
- ✅ Found 2 buttons and clicked "OK" button
- ❌ Discovered `.onetrust-banner-container` was NOT found/used

### Analysis:
- **Discovered selector was WRONG**: Found `.onetrust-banner-container` but actual element is `#onetrust-banner-sdk`
- **Success came from**: OneTrust-specific handler we added, not discovered selector
- **Effectiveness**: Discovered selector = 0% (didn't help)

---

## Longines Test

### Selectors Discovered in Phase 1.5:
1. `#usercentrics-root` (95% cookie_script) - **DISCOVERED**

### What Actually Worked:
- ❌ `#usercentrics-root` - **NOT FOUND in DOM** (timing issue)
- ✅ Used: `button[class*="accept"]` - **FALLBACK pattern, not discovered**
- ✅ Successfully clicked accept button

### Analysis:
- **Discovered selector exists but**: Not in DOM when checked (loads dynamically)
- **Success came from**: General fallback pattern, not discovered selector
- **Effectiveness**: Discovered selector = 0% (didn't help)

---

## Key Findings

1. **Discovered selectors are often incorrect or not available**:
   - VS: Wrong selector (container vs SDK)
   - Longines: Right selector but wrong timing

2. **Success is coming from fallbacks, not discoveries**:
   - OneTrust-specific handler (not from discovery)
   - General cookie button patterns (not from discovery)

3. **High z-index selectors are mostly noise**:
   - Many discovered but not useful for popup dismissal
   - They're often header/navigation elements

## Recommendations

1. **Improve selector discovery accuracy**:
   - Better matching of actual DOM elements
   - Wait for dynamic elements to load
   - Verify selectors exist before storing

2. **Better use of discovered selectors**:
   - Try discovered selectors with retries/waiting
   - Use discovered selectors as hints for fallback patterns
   - Track which discovered selectors actually work

3. **Separate useful from noise**:
   - Filter out header/navigation high z-index elements
   - Focus on cookie_framework/cookie_script types
   - Better confidence scoring
