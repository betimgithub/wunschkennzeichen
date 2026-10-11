--[[
    Halloween Farm (mit Overlay)
    1) Trick or Treat: läuft alle gespawnten "Trick or Treat!"-Flächen ab,
       bleibt auf jeder stehen, bis "Come back soon" erscheint, und geht
       dann zur nächsten. Flächen im Cooldown werden übersprungen und
       besucht, sobald sie wieder bereit sind.
    2) Auto-Hatch: öffnet parallel "Creaking Egg" und "Halloween Chest".

    Bedienung über das Overlay:
      - Knöpfe schalten Trick or Treat / Auto-Hatch an und aus
      - Titelleiste ziehen = Fenster verschieben
      - X = Skript komplett beenden
      - RightShift = Overlay ein-/ausblenden
    Erneutes Ausführen beendet automatisch die alte Instanz.
]]

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local UserInputService = game:GetService("UserInputService")
local player = Players.LocalPlayer

------------------------------------------------------------------------
-- KONFIGURATION
------------------------------------------------------------------------
local CONFIG = {
    TrickOrTreat = {
        AutoStart = false,               -- true = beim Ausführen direkt starten
        ReadyText = "trick or treat",    -- Text, wenn die Fläche bereit ist
        CooldownText = "come back soon", -- Text nach dem Klopfen
        MinStandTime = 3,                -- Animation dauert ca. 3 Sekunden
        MaxStandTime = 10,               -- Abbruch, falls "Come back soon" nie kommt
        SkipFailedFor = 30,              -- fehlgeschlagene Fläche so lange ignorieren (s)
        HeightOffset = 3,                -- Abstand über der Fläche beim Teleport
        ScanDelay = 1,                   -- Pause, wenn gerade keine Fläche bereit ist
        Debug = true,                    -- gefundene Flächen im Output anzeigen
    },

    Hatch = {
        AutoStart = false,
        -- "Remote": feuert ein RemoteEvent / ruft eine RemoteFunction auf
        -- "Prompt": löst den E-ProximityPrompt direkt aus (braucht fireproximityprompt)
        Mode = "Remote",

        -- Nur für Mode = "Remote": Pfad ab ReplicatedStorage
        -- z. B. ReplicatedStorage.Remotes.HatchEgg -> { "Remotes", "HatchEgg" }
        RemotePath = { "REMOTE_ORDNER", "REMOTE_NAME" },

        -- Was geöffnet werden soll. Nicht gewünschte Einträge einfach löschen.
        Targets = { "Creaking Egg", "Halloween Chest" },

        -- Zusätzliche Argumente nach dem Namen, z. B. { 1 } für die Anzahl.
        -- Gesendet wird: FireServer("Creaking Egg", table.unpack(ExtraArgs))
        ExtraArgs = {},

        Interval = 1,   -- Sekunden zwischen zwei Aufrufen
        Verbose = false,
    },

    ToggleGuiKey = Enum.KeyCode.RightShift,
}
------------------------------------------------------------------------

local runId = (_G.HalloweenFarmRun or 0) + 1
_G.HalloweenFarmRun = runId
local function running()
    return _G.HalloweenFarmRun == runId
end

-- An/Aus-Zustand der Funktionen (wird von den Knöpfen gesetzt)
local state = {
    TrickOrTreat = CONFIG.TrickOrTreat.AutoStart,
    Hatch = CONFIG.Hatch.AutoStart,
}

-- Wird unten beim Bau des Overlays ersetzt
local ui = {
    setStatus = function(_key, _text) end,
    refresh = function() end,
}

local function log(...)
    print("[HalloweenFarm]", ...)
end

------------------------------------------------------------------------
-- Trick or Treat
------------------------------------------------------------------------

local function totActive()
    return running() and state.TrickOrTreat
end

local function textOf(obj)
    if obj:IsA("TextLabel") or obj:IsA("TextButton") then
        local t = obj.ContentText ~= "" and obj.ContentText or obj.Text
        return string.lower(t)
    end
end

-- Liest alle sichtbaren Texte eines BillboardGuis aus
local function guiState(gui)
    local ready, cooldown = false, false
    if not gui.Parent or not gui.Enabled then
        return false, false
    end
    for _, obj in ipairs(gui:GetDescendants()) do
        local t = textOf(obj)
        if t and obj.Visible then
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
        for _, obj in ipairs(root:GetDescendants()) do
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

local function standPosition(part)
    return part.Position + Vector3.new(0, part.Size.Y / 2 + CONFIG.TrickOrTreat.HeightOffset, 0)
end

local failedUntil = {}
local visited = 0

local function visitPad(pad, hrp)
    local cfg = CONFIG.TrickOrTreat
    local target = standPosition(pad.part)
    local radius = math.max(math.min(pad.part.Size.X, pad.part.Size.Z) / 2, 2)

    hrp.CFrame = CFrame.new(target)
    hrp.AssemblyLinearVelocity = Vector3.zero

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
            hrp.CFrame = CFrame.new(target)
            hrp.AssemblyLinearVelocity = Vector3.zero
        end
        task.wait(0.2)
    end
end

local function trickOrTreatLoop()
    local cfg = CONFIG.TrickOrTreat
    local announced = false
    while running() do
        if not state.TrickOrTreat then
            ui.setStatus("TrickOrTreat", "Aus | Besucht: " .. visited)
            task.wait(0.3)
            continue
        end

        local char = player.Character
        local hrp = char and char:FindFirstChild("HumanoidRootPart")
        local humanoid = char and char:FindFirstChildOfClass("Humanoid")
        if not hrp or not humanoid or humanoid.Health <= 0 then
            ui.setStatus("TrickOrTreat", "Warte auf Charakter...")
            task.wait(1)
            continue
        end

        local all = scanPads()
        if cfg.Debug and not announced then
            log(#all .. " Trick-or-Treat-Flächen gefunden")
            for _, pad in ipairs(all) do log("  " .. pad.part:GetFullName()) end
            announced = true
        end

        -- Nur bereite Flächen, die nicht gerade gesperrt sind
        local now = os.clock()
        local ready = {}
        for _, pad in ipairs(all) do
            if (failedUntil[pad.gui] or 0) < now and (guiState(pad.gui)) then
                table.insert(ready, pad)
            end
        end

        if #ready == 0 then
            ui.setStatus("TrickOrTreat", string.format("0/%d bereit, warte | Besucht: %d", #all, visited))
            task.wait(cfg.ScanDelay)
            continue
        end

        -- Nächstgelegene zuerst -> kurze Wege durch die ganze Zone
        table.sort(ready, function(a, b)
            return (a.part.Position - hrp.Position).Magnitude < (b.part.Position - hrp.Position).Magnitude
        end)
        visitPad(ready[1], hrp)
    end
end

------------------------------------------------------------------------
-- Auto-Hatch
------------------------------------------------------------------------

local function resolveRemote(path)
    local current = ReplicatedStorage
    for _, name in ipairs(path) do
        current = current:WaitForChild(name, 10)
        if not current then
            return nil, "nicht gefunden: " .. name
        end
    end
    return current
end

-- Sucht den ProximityPrompt (E-Taste) eines Eies / einer Chest
local function findPrompt(targetName)
    local lowerTarget = string.lower(targetName)
    for _, obj in ipairs(workspace:GetDescendants()) do
        if obj:IsA("ProximityPrompt") then
            local haystack = string.lower(obj.ObjectText .. " " .. obj.ActionText .. " " .. obj:GetFullName())
            if string.find(haystack, lowerTarget, 1, true) then
                return obj
            end
        end
    end
end

-- Liefert eine Funktion fire(target) oder nil + Fehlermeldung
local function buildFire()
    local cfg = CONFIG.Hatch
    if cfg.Mode == "Prompt" then
        if typeof(fireproximityprompt) ~= "function" then
            return nil, "fireproximityprompt fehlt"
        end
        local prompts = {}
        return function(target)
            local prompt = prompts[target]
            if not prompt or not prompt.Parent then
                prompt = findPrompt(target)
                prompts[target] = prompt
            end
            if not prompt then error("kein ProximityPrompt für " .. target) end
            fireproximityprompt(prompt)
        end
    end

    local remote, err = resolveRemote(cfg.RemotePath)
    if not remote then
        return nil, "Remote " .. err
    end
    local isFunction = remote:IsA("RemoteFunction")
    if not (isFunction or remote:IsA("RemoteEvent") or remote:IsA("UnreliableRemoteEvent")) then
        return nil, remote.Name .. " ist kein Remote"
    end
    log("Auto-Hatch über " .. remote:GetFullName())
    return function(target)
        if isFunction then
            return remote:InvokeServer(target, table.unpack(cfg.ExtraArgs))
        end
        remote:FireServer(target, table.unpack(cfg.ExtraArgs))
    end
end

local function hatchLoop()
    local cfg = CONFIG.Hatch
    local fire
    local count = 0

    while running() do
        if not state.Hatch then
            ui.setStatus("Hatch", "Aus | Gesendet: " .. count)
            task.wait(0.3)
            continue
        end

        if not fire then
            ui.setStatus("Hatch", "Suche Remote/Prompt...")
            local err
            fire, err = buildFire()
            if not fire then
                warn("[HalloweenFarm] " .. err)
                state.Hatch = false
                ui.refresh()
                ui.setStatus("Hatch", "Fehler: " .. err)
                task.wait(3)
                continue
            end
        end

        for _, target in ipairs(cfg.Targets) do
            if not (running() and state.Hatch) then break end
            local ok, result = pcall(fire, target)
            if ok then
                count += 1
                ui.setStatus("Hatch", target .. " | Gesendet: " .. count)
                if cfg.Verbose then
                    log("Hatch gesendet: " .. target .. (result ~= nil and (" -> " .. tostring(result)) or ""))
                end
            else
                warn("[HalloweenFarm] Hatch-Fehler (" .. target .. "): " .. tostring(result))
                ui.setStatus("Hatch", "Fehler bei " .. target)
            end
            task.wait(cfg.Interval)
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

    local frame = Instance.new("Frame")
    frame.Size = UDim2.fromOffset(250, 196)
    frame.Position = UDim2.new(0, 20, 0.35, 0)
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

    local buttons, statusLabels = {}, {}

    local function makeRow(key, label, y)
        local btn = Instance.new("TextButton")
        btn.Size = UDim2.new(1, -20, 0, 34)
        btn.Position = UDim2.fromOffset(10, y)
        btn.Font = Enum.Font.GothamBold
        btn.TextSize = 14
        btn.TextColor3 = Color3.new(1, 1, 1)
        btn.AutoButtonColor = true
        btn.Parent = frame
        Instance.new("UICorner", btn).CornerRadius = UDim.new(0, 8)
        buttons[key] = { button = btn, label = label }

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
        statusLabels[key] = status

        table.insert(connections, btn.MouseButton1Click:Connect(function()
            state[key] = not state[key]
            ui.refresh()
        end))
    end

    makeRow("TrickOrTreat", "Trick or Treat", 36)
    makeRow("Hatch", "Auto-Hatch", 98)

    local hint = Instance.new("TextLabel")
    hint.Size = UDim2.new(1, -20, 0, 16)
    hint.Position = UDim2.fromOffset(10, 172)
    hint.BackgroundTransparency = 1
    hint.Font = Enum.Font.Gotham
    hint.TextSize = 11
    hint.TextColor3 = Color3.fromRGB(130, 125, 145)
    hint.TextXAlignment = Enum.TextXAlignment.Left
    hint.Text = CONFIG.ToggleGuiKey.Name .. " = ein-/ausblenden"
    hint.Parent = frame

    ui.refresh = function()
        for key, entry in pairs(buttons) do
            local on = state[key]
            entry.button.Text = entry.label .. (on and ":  AN" or ":  AUS")
            entry.button.BackgroundColor3 = on and Color3.fromRGB(46, 160, 67) or Color3.fromRGB(170, 50, 50)
        end
    end
    ui.setStatus = function(key, text)
        local lbl = statusLabels[key]
        if lbl and lbl.Parent then lbl.Text = text end
    end
    ui.refresh()

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

buildGui()
task.spawn(hatchLoop)
task.spawn(trickOrTreatLoop)
log("gestartet")
