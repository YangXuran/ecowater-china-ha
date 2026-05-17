# Ecowater China (怡口智控) — Home Assistant Integration

[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz/docs/faq/custom_repositories)
[![HA Version](https://img.shields.io/badge/Home%20Assistant-2024.5%2B-41BDF5)](https://www.home-assistant.io/)

Reverse-engineered Home Assistant custom integration for **Ecowater (怡口) V80ECM water softener** via the WeChat mini-program cloud API (`iot2.chinaecowater.com`).

> ⚠️ **This is an unofficial community reverse-engineering project.** Not affiliated with Ecowater or 怡口中国. Use at your own risk.

## Features

- 🌊 **15 sensors** — flow rate, water volume, regeneration status, hardness, signal strength
- 🔄 **Regeneration tracking** — real-time stage monitoring (backwash → brine draw → rinse)
- 📊 **Daily statistics** — daily water usage and averages
- ⚡ **Remote regeneration trigger** (one command away — PR welcome!)
- 🔐 **Charles Proxy-free running** — once `customer_id` is obtained, no proxy needed

## Installation

### HACS (Recommended)

1. Add custom repository: `https://github.com/YangXuran/ecowater-china-ha`
2. Search "Ecowater China" in HACS → Install
3. Restart Home Assistant
4. Go to **Settings → Devices & Services → Add Integration → Ecowater China**

### Manual

```bash
cd /path/to/ha/config/custom_components
git clone https://github.com/YangXuran/ecowater-china-ha.git ecowater_china
# Restart Home Assistant
```

## Configuration

The integration requires two values:

| Field | Description |
|-------|-------------|
| **Phone Number** | The phone number used to log into the 怡口智控 WeChat mini-program |
| **Customer ID** | A permanent UUID-like token assigned by Ecowater's backend |

### 🔑 How to get your `customer_id`

The `customer_id` is a **permanent identifier** assigned to your Ecowater account. It never changes. You only need to capture it once.

#### Method 1: Charles Proxy (macOS / Windows)

This is the method used to reverse-engineer this integration.

1. **Install Charles Proxy** — https://www.charlesproxy.com/ (free trial works)

2. **Configure SSL Proxying:**
   - Proxy → SSL Proxying Settings → Add
   - Host: `*.chinaecowater.com` Port: `443`

3. **Install Charles root certificate on your phone:**
   - Help → SSL Proxying → Install Charles Root Certificate on a Mobile Device
   - Follow the on-screen instructions (makes your phone trust Charles' certificate)
   - **Important:** On iOS, go to Settings → General → About → Certificate Trust Settings and enable the Charles certificate

4. **Connect your phone to Charles:**
   - Set phone WiFi proxy to your Mac's IP, port `8888`
   - Charles will prompt — click **Allow**

5. **Capture the `customer_id`:**
   - Open WeChat → 怡口智控 mini-program → Log in with your phone
   - In Charles, look for requests to `iot2.chinaecowater.com`
   - Find any authenticated request (e.g. `cusDevListByMC3`)
   - In the **Request Headers**, find: `ewtoken: customer{xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx}`
   - The part after `customer` is your `customer_id`

```
Example header:
  ewtoken: customerxxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
                            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                            This is your customer_id
```

#### Method 2: mitmproxy (Cross-platform, Free)

```bash
# Install
pip install mitmproxy

# Start proxy
mitmweb --listen-port 8888

# Then follow similar steps as Charles (install cert, route phone traffic)
```

#### Method 3: Stream / Packet Capture (Android only)

On Android, apps like **HttpCanary** or **Packet Capture** can capture SSL traffic from WeChat without root. Install the certificate, filter `chinaecowater.com`, and copy the `ewtoken` header value.

> **Once captured, your `customer_id` never expires.** You can uninstall the proxy after this step.

---

## API Documentation

**Base URL:** `https://iot2.chinaecowater.com`

**Authentication:** Every request requires header:
```
ewtoken: customer{your_customer_id}
```

### Core Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/applets/cusDev/cusDevListByMC3` | POST | Device real-time data (all `dataXX` fields) |
| `/api/applets/cusDev/cusDevListByMC3New` | POST | Newer device data endpoint (more fields) |
| `/api/app/statiscal/observe/daily` | POST | Today's hourly water usage breakdown |
| `/api/app/statiscal/daily` | POST | Daily water statistics |
| `/api/applets/model/cusLoadConifgsByMac` | GET | Device configuration (hex-encoded) |
| `/api/applets/device/control` | POST | Device control (trigger regeneration) |
| `/api/applets/cusDevFault/list` | POST | Fault/error logs |
| `/api/applets/customer/getCustomer` | POST | Convert openid → customer_id |
| `/api/applets/customer/openid` | POST | Convert WeChat code → openid |

### Device State Request

```
POST /api/applets/cusDev/cusDevListByMC3
Headers:
  ewtoken: customer{id}
  Content-Type: application/x-www-form-urlencoded
Body:
  customer={phone}&modelCode=
```

Response returns an array of devices with `data00` through `data75` fields.

---

## Data Field Mapping

### ✅ Confirmed Fields (15 sensors implemented)

| Field | Sensor Name | Unit | How Confirmed | Notes |
|-------|-------------|------|---------------|-------|
| `data0A` | Instant Flow Rate | L/min | Mini-program comparison ✅ | Updates in real-time when water is running |
| `data25` | Regeneration Count | times | Mini-program comparison ✅ | Lifetime count, never resets |
| `data2C` | Available Soft Water | L | Mini-program comparison ✅ | Resets to max after each regeneration |
| `data08` | Regeneration Active | — | Regeneration capture | `0` = idle, `1` = regenerating |
| `data24` | Regeneration Stage | — | Full cycle capture | See [Regeneration Stages](#regeneration-stages) |
| `data22` | Segment Water Use | L | Regeneration tracking | Resets each regeneration cycle |
| `data23` | Segment Count | — | Regeneration tracking | Resets each regeneration cycle |
| `data28` | Cumulative Water Use | L | Continuous tracking | Monotonic increase |
| `data29` | Daily Avg Water Use | L | Calculated inference | May be server-side calculation |
| `data13` | Total Water Use | L | Inference | Likely lifetime total |
| `data00` | Device Status | — | Inference | `255` = normal |
| `data0F` | Online | — | Inference | `1` = online |
| `data2B` | Salt Remaining Days | days | Inference | Estimated from salt level sensor |
| `data5A` | Inlet Hardness | — | Config comparison | Raw value × 10 = display (17 → 170) |
| `data60` | Signal Strength | dBm | Inference | WiFi/4G signal quality |

### 🔬 Regeneration Stages (`data24`)

| Value | Stage | Duration (typical) | Captured |
|-------|-------|--------------------|----------|
| `0` | Idle | — | ✅ |
| `1` | Backwash (反洗) | ~2-3 min | ❌ (too short to capture) |
| `2` | Brine Draw (吸盐) | ~50 min | ✅ |
| `3` | Slow Rinse (慢洗) | ~3-5 min | ✅ |
| `4` | Fast Rinse (快洗) | ~1-2 min | ✅ |

### ❓ Unconfirmed / Unknown Fields

These fields appeared in the API response but have **not** been mapped to a physical meaning. **Help wanted!**

| Field | Observed Values | Suspicion | How to Confirm |
|-------|-----------------|-----------|----------------|
| `data01` | — | Device subtype? | Compare with mini-program |
| `data02` | — | Firmware version? | Cross-reference with settings |
| `data03`-`data07` | — | Unknown | — |
| `data09` | — | Peak flow rate? | Run water at max flow |
| `data0B`-`data0E` | — | Unknown | — |
| `data10`-`data12` | — | Unknown | — |
| `data14`-`data21` | — | Unknown | — |
| `data26`-`data27` | — | Unknown | — |
| `data2A` | — | Unknown | — |
| `data2D`-`data2F` | — | Unknown | — |
| `data30`-`data59` | — | Unknown; config-related? | Compare with `cusLoadConifgsByMac` |
| `data5B`-`data5F` | — | Unknown | — |
| `data61`-`data75` | — | Unknown | — |

> 💡 **Tip for mapping unknown fields:** Watch the values change while performing specific actions:
> - Run water at a known flow rate → compare with flow meter
> - Trigger regeneration → watch which fields change at each stage
> - Change hardness setting in mini-program → see which hex config field changes

### Configuration API (Hex-Encoded)

Settings are stored as hex strings. Known mappings:

| Config Key | Hex in API | Related dataXX | Display Value | Unit |
|------------|-----------|----------------|---------------|------|
| Hardness (硬度) | `"5A"` → 90 | data5A=17 | 170 | (×10) |
| Regeneration Time (再生时间) | `"51"` → 81 | — | 2:00 AM | (time encode?) |
| Backwash Duration (反冲时间) | `"53"` → 3 | data53=3 | 3 min | minute |
| Fast Rinse Duration (快洗时间) | `"55"` → 1 | data55=1 | 1 min | minute |
| Salt Efficiency Mode (盐效模式) | `"5D"` | — | — | — |
| Low Temp Switch (低温开关) | `"46"` | — | — | — |

> ⚠️ **The time encoding is not yet fully decoded.** Hex `"51"` = decimal 81 somehow maps to 2:00 AM. PR welcome!

---

## Device Control

Trigger an immediate regeneration:

```
POST /api/applets/device/control
Headers:
  ewtoken: customer{id}
  Content-Type: application/x-www-form-urlencoded
Body:
  mac={device_mac}&02=1
```

| Command Code | Action |
|-------------|--------|
| `02=1` | Immediate regeneration |

Other command codes are unknown — potentially: vacation mode, bypass valve, manual backwash.

---

## Credentials & Security

- **`customer_id`** is a **permanent, non-expiring UUID**. Obtain once, use forever.
- **Phone number** is used as the account identifier in API requests.
- No password or WeChat session is needed after obtaining the `customer_id`.
- The `ewtoken` header is simply `customer{customer_id}` — no OAuth refresh required.

> 🔒 Never commit your `customer_id` or phone number to public repos. The integration uses Home Assistant's config entry system to store these securely.

---

## Contributing

This is a **community reverse-engineering project**. There's still a lot to discover:

### 🔥 High Priority

- [ ] **Map unknown `dataXX` fields** (see table above)
- [ ] **Decode config time format** (hex → HH:MM mapping)
- [ ] **Capture Stage 1 (Backwash)** — need to start Charles before regeneration begins
- [ ] **Add `switch` platform** — trigger regeneration from HA dashboard
- [ ] **Add `number` platform** — adjust hardness setting from HA

### 🧪 Medium Priority

- [ ] Discover other device control command codes
- [ ] Add `cusDevListByMC3New` endpoint support (may expose more fields)
- [ ] Unit confirmation: is hardness in ppm or gpg? (170 ppm ≈ 10 gpg)
- [ ] Fault code mapping (error codes → human-readable descriptions)
- [ ] Multi-device support (multiple softeners on one account)
- [ ] Add diagnostic sensors (last regeneration time, next scheduled)

### 📝 How to Contribute

1. Fork the repo
2. Set up Charles Proxy on your Ecowater device
3. Capture data while changing settings / triggering events
4. Document your findings
5. Submit a PR with field mappings or code improvements

### Methodology Reference

The original reverse engineering was done with:

- **Charles Proxy** — SSL man-in-the-middle on macOS
- **iPhone + WeChat** — capturing 怡口智控 mini-program traffic
- **326 requests captured** in `.chlz` format, including a full regeneration cycle
- **Field mapping** by comparing API values side-by-side with mini-program screenshots

---

## Compatibility

- **Home Assistant:** 2024.5+
- **Device tested:** Ecowater V80ECM (modelCode: `000400`)
- **Other models:** Likely compatible if they use the same mini-program (V60, V100, etc.) — please report!

---

## License

MIT

---

## Acknowledgments

- The Home Assistant community for the amazing integration framework
- Charles Proxy for making SSL interception accessible
- Ecowater for building solid hardware (now if only they'd publish an API... 😅)
