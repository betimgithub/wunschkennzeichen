--[[
    Halloween Farm (mit Overlay)

    1) Trick or Treat: läuft alle gespawnten "Trick or Treat!"-Flächen ab,
       bleibt auf jeder stehen, bis "Come back soon" erscheint, und geht
       dann zur nächsten. Flächen im Cooldown werden übersprungen und
       besucht, sobald sie wieder bereit sind.
    2) Creaking Egg / Halloween Chest: Da sich das Ei nicht per Remote
       öffnen lässt, teleportiert das Skript zwischendurch zur gespeicherten
       Position, drückt E und läuft dann weiter zu den Häusern. Sind gerade
       keine Häuser bereit, wird die Wartezeit am Ei verbracht.

    Einrichtung (einmalig):
      - Neben das Creaking Egg stellen -> "Pos" in der Ei-Zeile drücken
      - Neben die Halloween Chest stellen -> "Pos" in der Chest-Zeile drücken
      Positionen werden gespeichert (falls der Executor writefile kann).

    Bedienung: Knöpfe = an/aus, Titelleiste ziehen = verschieben,
    X = beenden, RightShift = Overlay ein-/ausblenden.
]]

local Players = game:GetService("Players")
local UserInputService = game:GetService("UserInputService")
local HttpService = game:GetService("HttpService")
local player = Players.LocalPlayer

------------------------------------------------------------------------
-- KONFIGURATION
------------------------------------------------------------------------
local CONFIG = {
    TrickOrTreat = {
        ReadyText = "trick or treat",    -- Text, wenn die Fläche bereit ist
        CooldownText = "come back soon", -- Text nach dem Klopfen
        MinStandTime = 3,                -- Animation dauert ca. 3 Sekunden
        MaxStandTime = 10,               -- Abbruch, falls "Come back soon" nie kommt
        SkipFailedFor = 30,              -- fehlgeschlagene Fläche so lange ignorieren (s)
        HeightOffset = 3,                -- Abstand über der Fläche beim Teleport
        ScanDelay = 1,                   -- Pause, wenn gerade nichts zu tun ist
        Debug = true,                    -- gefundene Flächen im Output anzeigen
    },

    -- Orte, an denen E gedrückt wird. Reihenfolge = Priorität.
    Stations = {
        {
            Key = "Chest",
            Label = "Halloween Chest",
            Interval = 300,     -- alle X Sekunden hingehen
            Presses = 1,        -- wie oft E pro Besuch
            PressDelay = 2,     -- Sekunden nach jedem E (Animation)
            WhenIdle = false,   -- auch hingehen, wenn kein Haus bereit ist
        },
        {
            Key = "Egg",
            Label = "Creaking Egg",
            Interval = 30,
            Presses = 3,
            PressDelay = 4,     -- Hatch-Animation abwarten
            WhenIdle = true,    -- Wartezeit auf Häuser am Ei verbringen
        },
    },

    LoadDelay = 0.8,        -- nach Teleport warten, bis die Gegend geladen ist
    KeyHoldTime = 0.15,     -- wie lange E gedrückt wird (bei Hold-Prompts erhöhen)
    SaveFile = "halloween_farm_positions.json",
    ToggleGuiKey = Enum.KeyCode.RightShift,
}
------------------------------------------------------------------------

local runId = (_G.HalloweenFarmRun or 0) + 1
_G.HalloweenFarmRun = runId
local function running()
    return _G.HalloweenFarmRun == runId
end

-- An/Aus-Zustand (wird von den Knöpfen gesetzt), alles startet aus
local state = { TrickOrTreat = false }
local stations = {} -- Key -> { cfg, cframe, last, count }
for _, cfg in ipairs(CONFIG.Stations) do
    state[cfg.Key] = false
    stations[cfg.Key] = { cfg = cfg, cframe = nil, last = -math.huge, count = 0 }
end

-- Wird unten beim Bau des Overlays ersetzt
local ui = {
    setStatus = function(_key, _text) end,
    refresh = function() end,
}

local function log(...)
    print("[HalloweenFarm]", ...)
end

local function getRoot()
    local char = player.Character
    local hrp = char and char:FindFirstChild("HumanoidRootPart")
    local humanoid = char and char:FindFirstChildOfClass("Humanoid")
    if hrp and humanoid and humanoid.Health > 0 then
        return hrp
    end
end

local function teleport(hrp, cframe)
    hrp.CFrame = cframe
    hrp.AssemblyLinearVelocity = Vector3.zero
end

------------------------------------------------------------------------
-- Positionen speichern / laden
------------------------------------------------------------------------

local function savePositions()
    if typeof(writefile) ~= "function" then return end
    local data = {}
    for key, st in pairs(stations) do
        if st.cframe then data[key] = { st.cframe:GetComponents() } end
    end
    pcall(function() writefile(CONFIG.SaveFile, HttpService:JSONEncode(data)) end)
end

local function loadPositions()
    if typeof(readfile) ~= "function" or typeof(isfile) ~= "function" then return end
    pcall(function()
        if not isfile(CONFIG.SaveFile) then return end
        local data = HttpService:JSONDecode(readfile(CONFIG.SaveFile))
        for key, comps in pairs(data) do
            if stations[key] and #comps == 12 then
                stations[key].cframe = CFrame.new(table.unpack(comps))
            end
        end
    end)
end

------------------------------------------------------------------------
-- E drücken (VirtualInputManager, sonst keypress)
------------------------------------------------------------------------

local VirtualInputManager
pcall(function() VirtualInputManager = game:GetService("VirtualInputManager") end)

local function pressE()
    if VirtualInputManager then
        local ok = pcall(function()
            VirtualInputManager:SendKeyEvent(true, Enum.KeyCode.E, false, game)
            task.wait(CONFIG.KeyHoldTime)
            VirtualInputManager:SendKeyEvent(false, Enum.KeyCode.E, false, game)
        end)
        if ok then return true end
    end
    if typeof(keypress) == "function" and typeof(keyrelease) == "function" then
        local ok = pcall(function()
            keypress(0x45) -- E
            task.wait(CONFIG.KeyHoldTime)
            keyrelease(0x45)
        end)
        if ok then return true end
    end
    return false
end

------------------------------------------------------------------------
-- Stationen (Ei / Chest)
------------------------------------------------------------------------

local function visitStation(key, hrp)
    local st = stations[key]
    local cfg = st.cfg
    local active = function() return running() and state[key] and hrp.Parent ~= nil end

    teleport(hrp, st.cframe)
    ui.setStatus(key, "Teleportiert, lade...")
    task.wait(CONFIG.LoadDelay)

    for i = 1, cfg.Presses do
        if not active() then break end
        -- Position halten, falls man weggeschoben wurde
        if (hrp.Position - st.cframe.Position).Magnitude > 4 then
            teleport(hrp, st.cframe)
        end
        if not pressE() then
            state[key] = false
            ui.refresh()
            ui.setStatus(key, "Fehler: E-Taste kann nicht gesendet werden")
            warn("[HalloweenFarm] Weder VirtualInputManager noch keypress funktionieren")
            return
        end
        st.count += 1
        ui.setStatus(key, string.format("E gedrückt (%d/%d) | Gesamt: %d", i, cfg.Presses, st.count))
        task.wait(cfg.PressDelay)
    end
    st.last = os.clock()
    ui.setStatus(key, "Gesamt: " .. st.count .. " | nächster Besuch in " .. cfg.Interval .. "s")
end

local function stationReady(key)
    local st = stations[key]
    return running() and state[key] and st.cframe ~= nil
end

------------------------------------------------------------------------
-- Trick or Treat
------------------------------------------------------------------------

local function totActive()
    return running() and state.TrickOrTreat
end

-- pcall: gesperrte Objekte ("property is locked") einfach überspringen
local function textOf(obj)
    local ok, t = pcall(function()
        if obj:IsA("TextLabel") or obj:IsA("TextButton") then
            local text = obj.ContentText ~= "" and obj.ContentText or obj.Text
            return obj.Visible and string.lower(text) or nil
        end
    end)
    return ok and t or nil
end

-- Liest alle sichtbaren Texte eines BillboardGuis aus
local function guiState(gui)
    local ready, cooldown = false, false
    if not gui.Parent or not gui.Enabled then
        return false, false
    end
    for _, obj in ipairs(gui:GetDescendants()) do
        local t = textOf(obj)
        if t then
            if string.find(t, CONFIG.TrickOrTreat.ReadyText, 1, true) then ready = true end
            if string.find(t, CONFIG.TrickOrTreat.CooldownText, 1, true) then cooldown = true end
        end
    end
    return ready and not cooldown, cooldown
end

local function firstPart(model)
    return model.PrimaryPart or model:FindFirstChildWhichIsA("BasePart", true)
end

-- Findet das Teil, auf das man sich stellen muss
local function partForGui(gui)
    local adornee = gui.Adornee
    if adornee then
        if adornee:IsA("BasePart") then return adornee end
        if adornee:IsA("Attachment") then return adornee.Parent end
        if adornee:IsA("Model") then return firstPart(adornee) end
    end
    local parent = gui.Parent
    while parent and parent ~= workspace and parent ~= game do
        if parent:IsA("BasePart") then return parent end
        if parent:IsA("Attachment") and parent.Parent:IsA("BasePart") then return parent.Parent end
        if parent:IsA("Model") then return firstPart(parent) end
        parent = parent.Parent
    end
end

-- Sucht alle Trick-or-Treat-BillboardGuis (Workspace + PlayerGui)
local function scanPads()
    local pads, seen = {}, {}
    local roots = { workspace, player:FindFirstChildOfClass("PlayerGui") }
    for _, root in ipairs(roots) do
        local ok, descendants = pcall(function() return root:GetDescendants() end)
        for _, obj in ipairs(ok and descendants or {}) do
            local t = textOf(obj)
            if t and (string.find(t, CONFIG.TrickOrTreat.ReadyText, 1, true)
                or string.find(t, CONFIG.TrickOrTreat.CooldownText, 1, true)) then
                local gui = obj:FindFirstAncestorWhichIsA("BillboardGui")
                    or obj:FindFirstAncestorWhichIsA("SurfaceGui")
                if gui and not seen[gui] then
                    seen[gui] = true
                    local part = partForGui(gui)
                    if part then
                        table.insert(pads, { gui = gui, part = part })
                    end
                end
            end
        end
    end
    return pads
end

local failedUntil = {}
local visited = 0
local announced = false

-- Nächstgelegene bereite Fläche (oder nil) + Anzahl gefundener Flächen
local function nextReadyPad(hrp)
    local all = scanPads()
    if CONFIG.TrickOrTreat.Debug and not announced then
        log(#all .. " Trick-or-Treat-Flächen gefunden")
        for _, pad in ipairs(all) do log("  " .. pad.part:GetFullName()) end
        announced = true
    end

    local now = os.clock()
    local best, bestDist = nil, math.huge
    for _, pad in ipairs(all) do
        if (failedUntil[pad.gui] or 0) < now and (guiState(pad.gui)) then
            local dist = (pad.part.Position - hrp.Position).Magnitude
            if dist < bestDist then best, bestDist = pad, dist end
        end
    end
    return best, #all
end

local function visitPad(pad, hrp)
    local cfg = CONFIG.TrickOrTreat
    local target = pad.part.Position + Vector3.new(0, pad.part.Size.Y / 2 + cfg.HeightOffset, 0)
    local radius = math.max(math.min(pad.part.Size.X, pad.part.Size.Z) / 2, 2)

    teleport(hrp, CFrame.new(target))

    local start = os.clock()
    while totActive() and hrp.Parent do
        local elapsed = os.clock() - start
        local _, cooldown = guiState(pad.gui)
        ui.setStatus("TrickOrTreat", string.format("Klopfe... %.1fs | Besucht: %d", elapsed, visited))

        if cooldown and elapsed >= cfg.MinStandTime then
            visited += 1
            if cfg.Debug then log(string.format("fertig: %s (%.1fs)", pad.part:GetFullName(), elapsed)) end
            return
        end
        if elapsed >= cfg.MaxStandTime or not pad.gui.Parent then
            warn("[HalloweenFarm] kein 'Come back soon' bei " .. pad.part:GetFullName() .. " – übersprungen")
            failedUntil[pad.gui] = os.clock() + cfg.SkipFailedFor
            return
        end

        -- Auf der Fläche bleiben, falls man runterfällt oder weggeschoben wird
        local offset = hrp.Position - target
        if Vector3.new(offset.X, 0, offset.Z).Magnitude > radius then
            teleport(hrp, CFrame.new(target))
        end
        task.wait(0.2)
    end
end

------------------------------------------------------------------------
-- Hauptschleife: ein Charakter, eine Aufgabe nach der anderen
------------------------------------------------------------------------

local function mainLoop()
    while running() do
        local hrp = getRoot()
        if not hrp then
            task.wait(1)
            continue
        end

        -- 1) Fällige Station (Chest / Ei)?
        local now = os.clock()
        local didStation = false
        for _, cfg in ipairs(CONFIG.Stations) do
            if stationReady(cfg.Key) and now - stations[cfg.Key].last >= cfg.Interval then
                visitStation(cfg.Key, hrp)
                didStation = true
                break
            end
        end
        if didStation then continue end

        -- 2) Bereites Haus?
        if state.TrickOrTreat then
            local pad, total = nextReadyPad(hrp)
            if pad then
                visitPad(pad, hrp)
                continue
            end
            ui.setStatus("TrickOrTreat", string.format("0/%d bereit, warte | Besucht: %d", total, visited))
        else
            ui.setStatus("TrickOrTreat", "Aus | Besucht: " .. visited)
        end

        -- 3) Nichts zu tun: Wartezeit an einer Station verbringen
        local idleStation
        for _, cfg in ipairs(CONFIG.Stations) do
            if cfg.WhenIdle and stationReady(cfg.Key) then
                idleStation = cfg.Key
                break
            end
        end
        if idleStation then
            visitStation(idleStation, hrp)
        else
            task.wait(CONFIG.TrickOrTreat.ScanDelay)
        end
    end
end

------------------------------------------------------------------------
-- Overlay
------------------------------------------------------------------------

local GUI_NAME = "HalloweenFarmGui"
local connections = {}

local function guiParents()
    local list = {}
    if typeof(gethui) == "function" then
        local ok, h = pcall(gethui)
        if ok and h then table.insert(list, h) end
    end
    pcall(function() table.insert(list, game:GetService("CoreGui")) end)
    table.insert(list, player:WaitForChild("PlayerGui"))
    return list
end

local function buildGui()
    -- Altes Overlay einer früheren Ausführung entfernen
    for _, parent in ipairs(guiParents()) do
        pcall(function()
            local old = parent:FindFirstChild(GUI_NAME)
            if old then old:Destroy() end
        end)
    end

    local screen = Instance.new("ScreenGui")
    screen.Name = GUI_NAME
    screen.ResetOnSpawn = false
    screen.ZIndexBehavior = Enum.ZIndexBehavior.Sibling
    screen.DisplayOrder = 999
    for _, parent in ipairs(guiParents()) do
        if pcall(function() screen.Parent = parent end) and screen.Parent then break end
    end

    local rows = { { key = "TrickOrTreat", label = "Trick or Treat" } }
    for _, cfg in ipairs(CONFIG.Stations) do
        table.insert(rows, { key = cfg.Key, label = cfg.Label, station = true })
    end

    local ROW_HEIGHT = 62
    local frame = Instance.new("Frame")
    frame.Size = UDim2.fromOffset(270, 36 + #rows * ROW_HEIGHT + 22)
    frame.Position = UDim2.new(0, 20, 0.3, 0)
    frame.BackgroundColor3 = Color3.fromRGB(28, 24, 36)
    frame.BorderSizePixel = 0
    frame.Parent = screen
    Instance.new("UICorner", frame).CornerRadius = UDim.new(0, 10)
    local stroke = Instance.new("UIStroke", frame)
    stroke.Color = Color3.fromRGB(255, 140, 0)
    stroke.Thickness = 1.5

    local title = Instance.new("TextLabel")
    title.Size = UDim2.new(1, 0, 0, 30)
    title.BackgroundTransparency = 1
    title.Text = "  Halloween Farm"
    title.TextXAlignment = Enum.TextXAlignment.Left
    title.Font = Enum.Font.GothamBold
    title.TextSize = 15
    title.TextColor3 = Color3.fromRGB(255, 160, 40)
    title.Parent = frame

    local close = Instance.new("TextButton")
    close.Size = UDim2.fromOffset(26, 22)
    close.Position = UDim2.new(1, -32, 0, 4)
    close.BackgroundColor3 = Color3.fromRGB(70, 60, 80)
    close.Text = "X"
    close.Font = Enum.Font.GothamBold
    close.TextSize = 13
    close.TextColor3 = Color3.new(1, 1, 1)
    close.Parent = frame
    Instance.new("UICorner", close).CornerRadius = UDim.new(0, 6)

    local buttons, posButtons, statusLabels = {}, {}, {}

    for index, row in ipairs(rows) do
        local y = 36 + (index - 1) * ROW_HEIGHT

        local btn = Instance.new("TextButton")
        btn.Size = row.station and UDim2.new(1, -78, 0, 34) or UDim2.new(1, -20, 0, 34)
        btn.Position = UDim2.fromOffset(10, y)
        btn.Font = Enum.Font.GothamBold
        btn.TextSize = 13
        btn.TextColor3 = Color3.new(1, 1, 1)
        btn.Parent = frame
        Instance.new("UICorner", btn).CornerRadius = UDim.new(0, 8)
        buttons[row.key] = { button = btn, label = row.label }

        local status = Instance.new("TextLabel")
        status.Size = UDim2.new(1, -20, 0, 18)
        status.Position = UDim2.fromOffset(10, y + 36)
        status.BackgroundTransparency = 1
        status.Font = Enum.Font.Gotham
        status.TextSize = 12
        status.TextColor3 = Color3.fromRGB(200, 200, 210)
        status.TextXAlignment = Enum.TextXAlignment.Left
        status.TextTruncate = Enum.TextTruncate.AtEnd
        status.Text = "-"
        status.Parent = frame
        statusLabels[row.key] = status

        table.insert(connections, btn.MouseButton1Click:Connect(function()
            if row.station and not stations[row.key].cframe then
                status.Text = "Erst neben " .. row.label .. " stellen und 'Pos' drücken"
                return
            end
            state[row.key] = not state[row.key]
            if row.station and state[row.key] then
                stations[row.key].last = -math.huge -- sofort einmal hingehen
            end
            ui.refresh()
        end))

        if row.station then
            local pos = Instance.new("TextButton")
            pos.Size = UDim2.fromOffset(58, 34)
            pos.Position = UDim2.new(1, -66, 0, y)
            pos.BackgroundColor3 = Color3.fromRGB(46, 120, 200)
            pos.Font = Enum.Font.GothamBold
            pos.TextSize = 12
            pos.TextColor3 = Color3.new(1, 1, 1)
            pos.Parent = frame
            Instance.new("UICorner", pos).CornerRadius = UDim.new(0, 8)
            posButtons[row.key] = pos

            table.insert(connections, pos.MouseButton1Click:Connect(function()
                local hrp = getRoot()
                if not hrp then return end
                stations[row.key].cframe = hrp.CFrame
                savePositions()
                status.Text = "Position gespeichert"
                ui.refresh()
            end))
        end
    end

    local hint = Instance.new("TextLabel")
    hint.Size = UDim2.new(1, -20, 0, 16)
    hint.Position = UDim2.new(0, 10, 1, -20)
    hint.BackgroundTransparency = 1
    hint.Font = Enum.Font.Gotham
    hint.TextSize = 11
    hint.TextColor3 = Color3.fromRGB(130, 125, 145)
    hint.TextXAlignment = Enum.TextXAlignment.Left
    hint.Text = CONFIG.ToggleGuiKey.Name .. " = ein-/ausblenden | Pos = Standort speichern"
    hint.Parent = frame

    ui.refresh = function()
        for key, entry in pairs(buttons) do
            local on = state[key]
            entry.button.Text = entry.label .. (on and ":  AN" or ":  AUS")
            entry.button.BackgroundColor3 = on and Color3.fromRGB(46, 160, 67) or Color3.fromRGB(170, 50, 50)
        end
        for key, pos in pairs(posButtons) do
            pos.Text = stations[key].cframe and "Pos ok" or "Pos"
        end
    end
    ui.setStatus = function(key, text)
        local lbl = statusLabels[key]
        if lbl and lbl.Parent then lbl.Text = text end
    end
    ui.refresh()
    for key, st in pairs(stations) do
        ui.setStatus(key, st.cframe and "Position geladen" or "Keine Position – 'Pos' drücken")
    end

    -- Fenster an der Titelleiste verschieben (Maus + Touch)
    local dragging, dragStart, startPos
    table.insert(connections, title.InputBegan:Connect(function(input)
        if input.UserInputType == Enum.UserInputType.MouseButton1
            or input.UserInputType == Enum.UserInputType.Touch then
            dragging, dragStart, startPos = true, input.Position, frame.Position
            input.Changed:Connect(function()
                if input.UserInputState == Enum.UserInputState.End then dragging = false end
            end)
        end
    end))
    table.insert(connections, UserInputService.InputChanged:Connect(function(input)
        if dragging and (input.UserInputType == Enum.UserInputType.MouseMovement
            or input.UserInputType == Enum.UserInputType.Touch) then
            local delta = input.Position - dragStart
            frame.Position = UDim2.new(startPos.X.Scale, startPos.X.Offset + delta.X,
                startPos.Y.Scale, startPos.Y.Offset + delta.Y)
        end
    end))

    -- Overlay ein-/ausblenden
    table.insert(connections, UserInputService.InputBegan:Connect(function(input, processed)
        if not processed and input.KeyCode == CONFIG.ToggleGuiKey then
            frame.Visible = not frame.Visible
        end
    end))

    -- X: alles beenden
    table.insert(connections, close.MouseButton1Click:Connect(function()
        screen:Destroy()
    end))

    -- Wird das Overlay zerstört (X oder neue Ausführung), stoppt diese Instanz
    screen.Destroying:Connect(function()
        if running() then _G.HalloweenFarmRun = nil end
        for _, c in ipairs(connections) do c:Disconnect() end
        log("beendet")
    end)
end

------------------------------------------------------------------------
-- Start
------------------------------------------------------------------------

loadPositions()
buildGui()
task.spawn(mainLoop)
log("gestartet")
