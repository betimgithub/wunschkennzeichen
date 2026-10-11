--[[
    Remote Finder
    Durchsucht ReplicatedStorage (rekursiv) nach RemoteEvents und
    RemoteFunctions sowie den Workspace nach ProximityPrompts (E-Taste),
    deren Name eines der Suchwörter enthält, und gibt sie im Output aus.

    Jedes Objekt wird einzeln in pcall geprüft: gesperrte Objekte
    ("property is locked", "lacking capability" ...) werden übersprungen,
    statt das ganze Skript abzubrechen.
]]

local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Players = game:GetService("Players")

-- Alle Zeilen werden gesammelt und am Ende in einem Fenster angezeigt,
-- weil manche Executors print() nicht in die F9-Konsole schreiben.
local lines = {}
local rawPrint = print
local function print(text)
    table.insert(lines, text)
    rawPrint(text)
end
print("Remote Finder gestartet")

-- Suchwörter (Groß-/Kleinschreibung egal). Bei Bedarf erweitern.
local KEYWORDS = {
    "egg", "hatch", "buy", "open",
    "chest", "creaking", "halloween", "treat", "candy", "knock",
}

-- true = ALLE Remotes/Prompts ausgeben, ohne Filter (hilfreich, wenn die
-- Remotes kryptische Namen haben)
local SHOW_ALL = false

local function matchesKeyword(text)
    local lower = string.lower(text)
    for _, word in ipairs(KEYWORDS) do
        if string.find(lower, word, 1, true) then
            return true
        end
    end
    return false
end

local function safeDescendants(root)
    local ok, list = pcall(function() return root:GetDescendants() end)
    if ok then return list end
    print("[RemoteFinder] GetDescendants fehlgeschlagen für " .. tostring(root) .. ": " .. tostring(list))
    return {}
end

local skipped = 0

-- ReplicatedStorage: Remotes
local found = 0
print("========== Remotes in ReplicatedStorage ==========")
for _, obj in ipairs(safeDescendants(ReplicatedStorage)) do
    local ok, line = pcall(function()
        if obj:IsA("RemoteEvent") or obj:IsA("RemoteFunction") or obj:IsA("UnreliableRemoteEvent") then
            -- Auch den Pfad prüfen: oft heißt der Ordner "Eggs" und das Remote nur "Open"
            local path = obj:GetFullName()
            if SHOW_ALL or matchesKeyword(path) then
                return string.format("[%s] %s", obj.ClassName, path)
            end
        end
    end)
    if not ok then
        skipped += 1
    elseif line then
        found += 1
        print(line)
    end
end
print(string.format("========== %d Remotes ==========", found))

-- Workspace: ProximityPrompts (E-Taste) – zeigt, wie das Ei geöffnet wird
local prompts = 0
print("========== ProximityPrompts im Workspace ==========")
for _, obj in ipairs(safeDescendants(workspace)) do
    local ok, line = pcall(function()
        if obj:IsA("ProximityPrompt") then
            local path = obj:GetFullName()
            local objectText, actionText = "", ""
            pcall(function() objectText = obj.ObjectText end)
            pcall(function() actionText = obj.ActionText end)
            if SHOW_ALL or matchesKeyword(path .. " " .. objectText .. " " .. actionText) then
                return string.format("[Prompt] %s | ObjectText=%q ActionText=%q", path, objectText, actionText)
            end
        end
    end)
    if not ok then
        skipped += 1
    elseif line then
        prompts += 1
        print(line)
    end
end
print(string.format("========== %d Prompts ==========", prompts))

if skipped > 0 then
    print(string.format("(%d gesperrte Objekte übersprungen – normal, kein Problem)", skipped))
end

------------------------------------------------------------------------
-- Ergebnis-Fenster (mit Kopieren-Knopf)
------------------------------------------------------------------------
local result = table.concat(lines, "\n")

local parent
if typeof(gethui) == "function" then pcall(function() parent = gethui() end) end
if not parent then pcall(function() parent = game:GetService("CoreGui") end) end

local screen = Instance.new("ScreenGui")
screen.Name = "RemoteFinderGui"
screen.ResetOnSpawn = false
screen.DisplayOrder = 1000
if not (parent and pcall(function() screen.Parent = parent end) and screen.Parent) then
    screen.Parent = Players.LocalPlayer:WaitForChild("PlayerGui")
end

local frame = Instance.new("Frame")
frame.Size = UDim2.new(0.6, 0, 0.6, 0)
frame.Position = UDim2.new(0.2, 0, 0.2, 0)
frame.BackgroundColor3 = Color3.fromRGB(25, 25, 30)
frame.BorderSizePixel = 0
frame.Parent = screen
Instance.new("UICorner", frame).CornerRadius = UDim.new(0, 8)

local function button(text, xOffset, color)
    local b = Instance.new("TextButton")
    b.Size = UDim2.fromOffset(110, 26)
    b.Position = UDim2.new(1, xOffset, 0, 6)
    b.BackgroundColor3 = color
    b.TextColor3 = Color3.new(1, 1, 1)
    b.Font = Enum.Font.GothamBold
    b.TextSize = 13
    b.Text = text
    b.Parent = frame
    Instance.new("UICorner", b).CornerRadius = UDim.new(0, 6)
    return b
end

local title = Instance.new("TextLabel")
title.Size = UDim2.new(1, -250, 0, 38)
title.Position = UDim2.fromOffset(10, 0)
title.BackgroundTransparency = 1
title.TextXAlignment = Enum.TextXAlignment.Left
title.Font = Enum.Font.GothamBold
title.TextSize = 15
title.TextColor3 = Color3.fromRGB(255, 160, 40)
title.Text = "Remote Finder – Ergebnis"
title.Parent = frame

local copy = button("Kopieren", -236, Color3.fromRGB(46, 120, 200))
local close = button("Schließen", -120, Color3.fromRGB(170, 50, 50))

local scroll = Instance.new("ScrollingFrame")
scroll.Size = UDim2.new(1, -20, 1, -48)
scroll.Position = UDim2.fromOffset(10, 40)
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
box.TextSize = 13
box.TextColor3 = Color3.fromRGB(220, 220, 220)
box.Text = result
box.Parent = scroll

copy.MouseButton1Click:Connect(function()
    if typeof(setclipboard) == "function" then
        setclipboard(result)
        copy.Text = "Kopiert!"
    else
        copy.Text = "nicht verfügbar"
    end
end)
close.MouseButton1Click:Connect(function()
    screen:Destroy()
end)
