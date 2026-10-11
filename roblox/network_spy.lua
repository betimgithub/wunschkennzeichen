--[[
    Network Spy (ohne hookmetamethod, für Xeno)
    Das Spiel schickt alles über EIN Remote:
      ReplicatedStorage.Shared.Framework.Network.Remote.RemoteEvent
    Die Aktion (z. B. Ei öffnen) steckt in den Argumenten. Dieses Skript lädt
    die Network-Module des Spiels per require() und hängt sich in deren
    Funktionen ein. So sehen wir, was beim Drücken von E gesendet wird.

    So benutzen:
      1. Skript ausführen -> Fenster zeigt die gefundenen Module/Funktionen
      2. Zum Creaking Egg gehen und einmal E drücken
      3. Optional: Halloween Chest öffnen, einmal Trick or Treat machen
      4. "Kopieren" drücken und das Ergebnis schicken
]]

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local UserInputService = game:GetService("UserInputService")

local NETWORK_ROOT = { "Shared", "Framework", "Network" }
local MAX_ENTRIES = 200

------------------------------------------------------------------------
-- Fenster
------------------------------------------------------------------------

local entries = {}
local paused = false

local parent
if typeof(gethui) == "function" then pcall(function() parent = gethui() end) end
if not parent then pcall(function() parent = game:GetService("CoreGui") end) end

local screen = Instance.new("ScreenGui")
screen.Name = "NetworkSpyGui"
screen.ResetOnSpawn = false
screen.DisplayOrder = 1000
if not (parent and pcall(function() screen.Parent = parent end) and screen.Parent) then
    screen.Parent = Players.LocalPlayer:WaitForChild("PlayerGui")
end

local frame = Instance.new("Frame")
frame.Size = UDim2.fromOffset(480, 340)
frame.Position = UDim2.new(1, -500, 0.25, 0)
frame.BackgroundColor3 = Color3.fromRGB(25, 25, 30)
frame.BorderSizePixel = 0
frame.Parent = screen
Instance.new("UICorner", frame).CornerRadius = UDim.new(0, 8)

local title = Instance.new("TextLabel")
title.Size = UDim2.new(1, -20, 0, 30)
title.Position = UDim2.fromOffset(10, 0)
title.BackgroundTransparency = 1
title.TextXAlignment = Enum.TextXAlignment.Left
title.Font = Enum.Font.GothamBold
title.TextSize = 14
title.TextColor3 = Color3.fromRGB(255, 160, 40)
title.Text = "Network Spy – lade Module..."
title.Parent = frame

local function button(text, index, color)
    local b = Instance.new("TextButton")
    b.Size = UDim2.fromOffset(100, 24)
    b.Position = UDim2.fromOffset(10 + (index - 1) * 108, 32)
    b.BackgroundColor3 = color
    b.TextColor3 = Color3.new(1, 1, 1)
    b.Font = Enum.Font.GothamBold
    b.TextSize = 12
    b.Text = text
    b.Parent = frame
    Instance.new("UICorner", b).CornerRadius = UDim.new(0, 6)
    return b
end

local copyBtn = button("Kopieren", 1, Color3.fromRGB(46, 120, 200))
local pauseBtn = button("Pause", 2, Color3.fromRGB(90, 90, 110))
local clearBtn = button("Leeren", 3, Color3.fromRGB(90, 90, 110))
local closeBtn = button("Schließen", 4, Color3.fromRGB(170, 50, 50))

local scroll = Instance.new("ScrollingFrame")
scroll.Size = UDim2.new(1, -20, 1, -66)
scroll.Position = UDim2.fromOffset(10, 60)
scroll.BackgroundColor3 = Color3.fromRGB(15, 15, 18)
scroll.BorderSizePixel = 0
scroll.ScrollBarThickness = 8
scroll.AutomaticCanvasSize = Enum.AutomaticSize.Y
scroll.CanvasSize = UDim2.new()
scroll.Parent = frame

local box = Instance.new("TextBox")
box.Size = UDim2.new(1, -12, 0, 0)
box.AutomaticSize = Enum.AutomaticSize.Y
box.BackgroundTransparency = 1
box.ClearTextOnFocus = false
box.TextEditable = false
box.MultiLine = true
box.TextWrapped = true
box.TextXAlignment = Enum.TextXAlignment.Left
box.TextYAlignment = Enum.TextYAlignment.Top
box.Font = Enum.Font.Code
box.TextSize = 12
box.TextColor3 = Color3.fromRGB(220, 220, 220)
box.Text = ""
box.Parent = scroll

local function fullText()
    local out = {}
    for _, e in ipairs(entries) do
        table.insert(out, e.count > 1 and (e.line .. "  x" .. e.count) or e.line)
    end
    return table.concat(out, "\n")
end

local pending = false
local function refresh()
    if pending then return end
    pending = true
    task.delay(0.2, function()
        pending = false
        if box.Parent then
            box.Text = fullText()
            scroll.CanvasPosition = Vector2.new(0, 1e6)
        end
    end)
end

local function add(line)
    local last = entries[#entries]
    if last and last.line == line then
        last.count += 1
    else
        table.insert(entries, { line = line, count = 1 })
        if #entries > MAX_ENTRIES then table.remove(entries, 1) end
    end
    refresh()
end

copyBtn.MouseButton1Click:Connect(function()
    if typeof(setclipboard) == "function" then
        setclipboard(fullText())
        copyBtn.Text = "Kopiert!"
        task.delay(1.5, function() copyBtn.Text = "Kopieren" end)
    else
        copyBtn.Text = "nicht verfügbar"
    end
end)
pauseBtn.MouseButton1Click:Connect(function()
    paused = not paused
    pauseBtn.Text = paused and "Weiter" or "Pause"
end)
clearBtn.MouseButton1Click:Connect(function()
    table.clear(entries)
    refresh()
end)
closeBtn.MouseButton1Click:Connect(function()
    paused = true
    screen:Destroy()
end)

local dragging, dragStart, startPos
title.InputBegan:Connect(function(input)
    if input.UserInputType == Enum.UserInputType.MouseButton1
        or input.UserInputType == Enum.UserInputType.Touch then
        dragging, dragStart, startPos = true, input.Position, frame.Position
        input.Changed:Connect(function()
            if input.UserInputState == Enum.UserInputState.End then dragging = false end
        end)
    end
end)
UserInputService.InputChanged:Connect(function(input)
    if dragging and (input.UserInputType == Enum.UserInputType.MouseMovement
        or input.UserInputType == Enum.UserInputType.Touch) then
        local d = input.Position - dragStart
        frame.Position = UDim2.new(startPos.X.Scale, startPos.X.Offset + d.X, startPos.Y.Scale, startPos.Y.Offset + d.Y)
    end
end)

------------------------------------------------------------------------
-- Module laden und Funktionen umhüllen
------------------------------------------------------------------------

local function serialize(value, depth, selfTable)
    depth = depth or 0
    local t = typeof(value)
    if selfTable and value == selfTable then
        return "<self>"
    elseif t == "string" then
        return string.format("%q", value)
    elseif t == "Instance" then
        local ok, name = pcall(function() return value:GetFullName() end)
        return ok and name or "<Instance>"
    elseif t == "table" then
        if depth >= 3 then return "{...}" end
        local parts = {}
        for k, v in pairs(value) do
            table.insert(parts, "[" .. serialize(k, depth + 1) .. "] = " .. serialize(v, depth + 1))
            if #parts >= 25 then table.insert(parts, "...") break end
        end
        return "{" .. table.concat(parts, ", ") .. "}"
    elseif t == "function" then
        return "<function>"
    elseif t == "number" or t == "boolean" or t == "nil" then
        return tostring(value)
    else
        return t .. ".new(" .. tostring(value) .. ")"
    end
end

-- Bereits umhüllte Funktionen merken (falls das Skript mehrfach läuft)
_G.NetworkSpyWrapped = _G.NetworkSpyWrapped or {}
local wrapped = _G.NetworkSpyWrapped
_G.NetworkSpyLog = add -- neue Instanz übernimmt die Ausgabe

local function wrapTable(tbl, label)
    local names = {}
    for key, fn in pairs(tbl) do
        if type(fn) == "function" and type(key) == "string" then
            table.insert(names, key)
            if not wrapped[fn] then
                local original = fn
                local proxy = function(...)
                    if not paused and _G.NetworkSpyLog then
                        local args = table.pack(...)
                        local parts = {}
                        for i = 1, args.n do parts[i] = serialize(args[i], 0, tbl) end
                        pcall(_G.NetworkSpyLog, string.format("[%s.%s] (%s)", label, key, table.concat(parts, ", ")))
                    end
                    return original(...)
                end
                local ok = pcall(function() tbl[key] = proxy end)
                if ok then
                    wrapped[proxy] = true
                else
                    names[#names] = key .. "(gesperrt)"
                end
            end
        end
    end
    table.sort(names)
    return names
end

local root = ReplicatedStorage
for _, name in ipairs(NETWORK_ROOT) do
    root = root and root:FindFirstChild(name)
end

if not root then
    add("Network-Ordner nicht gefunden: ReplicatedStorage." .. table.concat(NETWORK_ROOT, "."))
else
    local modules = {}
    if root:IsA("ModuleScript") then table.insert(modules, root) end
    for _, obj in ipairs(root:GetDescendants()) do
        if obj:IsA("ModuleScript") then table.insert(modules, obj) end
    end
    add(string.format("Executor: %s | require: %s",
        typeof(identifyexecutor) == "function" and table.concat({ identifyexecutor() }, " ") or "?",
        tostring(typeof(require) == "function")))
    add(#modules .. " Module unter " .. root:GetFullName())

    local hooked = 0
    for _, ms in ipairs(modules) do
        local label = ms.Name
        local ok, result = pcall(require, ms)
        if not ok then
            add("  " .. ms:GetFullName() .. " -> require fehlgeschlagen: " .. tostring(result))
        elseif type(result) ~= "table" then
            add("  " .. ms:GetFullName() .. " -> " .. typeof(result))
        else
            local names = wrapTable(result, label)
            local mt = getmetatable(result)
            if type(mt) == "table" and type(mt.__index) == "table" and mt.__index ~= result then
                for _, n in ipairs(wrapTable(mt.__index, label)) do table.insert(names, n) end
            end
            hooked += #names
            add("  " .. ms:GetFullName() .. " -> " .. (#names > 0 and table.concat(names, ", ") or "(keine Funktionen)"))
        end
    end

    add("----------------------------------------")
    if hooked > 0 then
        title.Text = "Network Spy aktiv – drück jetzt E am Ei"
        add("Bereit. Jetzt E am Ei drücken – Aufrufe erscheinen hier:")
    else
        title.Text = "Network Spy – keine Funktionen gefunden"
    end
end
