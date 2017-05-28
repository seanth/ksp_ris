﻿using System;
using System.Net;
using System.Collections;
using System.Collections.Generic;
using System.Threading;
using UnityEngine;
using KSP.UI.Screens;

namespace ksp_ris
{
	public class YDate : IComparable
	{
		public int year;
		public int day;

		public YDate(int year, int day)
		{
			this.year = year;
			this.day = day;
		}

		public YDate(Hashtable ht)
		{
			this.year = (int)(double)ht["year"];
		        this.day = (int)(double)ht["day"];
		}

		public int CompareTo(YDate other)
		{
			if (other.year != year)
				return year.CompareTo(other.year);
			return day.CompareTo(other.day);
		}

		public int CompareTo(object obj)
		{
			if (obj == null)
				return 1;
			YDate other = obj as YDate;
			if (other == null)
				throw new ArgumentException("Object is not a YDate");
			return CompareTo(other);
		}

		public override string ToString()
		{
		        return String.Format("y{0:D}d{1:D3}", year, day);
		}
	}

	public class GameListEntry
	{
		public List<string> players;
		public YDate mindate;

		public GameListEntry(Hashtable ht)
		{
			mindate = new YDate(ht["mindate"] as Hashtable);
		        players = new List<string>();
		        foreach (object obj in ht["players"] as ArrayList) {
		                players.Add(obj as string);
		        }
		}
	}

	public class Server
	{
		public Dictionary<string,GameListEntry> gameList = null;
		public delegate void CancelDelegate();
		public delegate void ResultCallback(bool ok);

		public string host = "127.0.0.1";
		public UInt16 port = 8080;
		private Uri server { get { return new UriBuilder("http", host, port).Uri; } }

		public void Save(ConfigNode node)
		{
			node.AddValue("host", host);
			node.AddValue("port", port);
		}

		public void Load(ConfigNode node)
		{
			if (node.HasValue("host"))
				host = node.GetValue("host");
			if (node.HasValue("port"))
				UInt16.TryParse(node.GetValue("port"), out port);
		}

		public CancelDelegate ListGames(ResultCallback cb)
		{
			WebClient client = new WebClient();
			client.DownloadStringCompleted += (object sender, DownloadStringCompletedEventArgs e) => {
				bool result = false;
				try {
					if (e.Cancelled) {
						Logging.Log("ListGames cancelled");
					} else if (e.Error != null) {
						Logging.LogException(e.Error);
					} else {
						string json = e.Result;
						Logging.Log("ListGames: " + json);
						object obj = MiniJSON.jsonDecode(json);
						System.Collections.Hashtable ht = obj as Hashtable;
						gameList = new Dictionary<string, GameListEntry>();
						foreach (DictionaryEntry de in ht) {
							gameList.Add(de.Key.ToString(), new GameListEntry(de.Value as Hashtable));
						}
						Logging.LogFormat("Listed {0} games", gameList.Count);
						result = true;
					}
				} catch (Exception exc) {
					/* Job failed, but we still have to exit job state */
					Logging.LogException(exc);
				}
				cb.Invoke(result);
			};
			client.DownloadStringAsync(new Uri(server, "/?json=1"));
			return client.CancelAsync;
		}
	}

	[KSPAddon(KSPAddon.Startup.AllGameScenes, false)]
	public class RISCore : MonoBehaviour
	{
		public static RISCore Instance { get; protected set; }
		public Server server = new Server();
		private ApplicationLauncherButton button;
		private UI.MasterWindow masterWindow;

		public void Start()
		{
		        if (Instance != null) {
				Destroy(this);
				return;
			}

			Instance = this;
			masterWindow = new ksp_ris.UI.MasterWindow(server);
			if (ScenarioRIS.Instance != null)
				Load(ScenarioRIS.Instance.node);
			Logging.Log("RISCore loaded successfully.");
		}

		protected void Awake()
		{
			try {
				GameEvents.onGUIApplicationLauncherReady.Add(this.OnGuiAppLauncherReady);
			} catch (Exception ex) {
				Logging.LogException(ex);
			}
		}

		public void OnGUI()
		{
			GUI.depth = 0;

			Action windows = delegate { };
			foreach (var window in UI.AbstractWindow.Windows.Values)
				windows += window.Draw;
			windows.Invoke();
		}

		private void OnGuiAppLauncherReady()
		{
			try {
				button = ApplicationLauncher.Instance.AddModApplication(
					masterWindow.Show,
					HideGUI,
					null,
					null,
					null,
					null,
					ApplicationLauncher.AppScenes.ALWAYS,
					GameDatabase.Instance.GetTexture("RIS/Textures/toolbar_icon", false));
				GameEvents.onGameSceneLoadRequested.Add(this.OnSceneChange);
			} catch (Exception ex) {
				Logging.LogException(ex);
			}
		}

		private void HideGUI()
		{
			masterWindow.Hide();
		}

		private void OnSceneChange(GameScenes s)
		{
			if (s != GameScenes.FLIGHT)
				HideGUI();
		}

		public void OnDestroy()
		{
			Instance = null;
			try {
				GameEvents.onGUIApplicationLauncherReady.Remove(this.OnGuiAppLauncherReady);
				if (button != null)
					ApplicationLauncher.Instance.RemoveModApplication(button);
			} catch (Exception ex) {
				Logging.LogException(ex);
			}
		}

		public void Save(ConfigNode node)
		{
			ConfigNode sn = node.AddNode("server");
			server.Save(sn);
		}

		public void Load(ConfigNode node)
		{
			if (node.HasNode("server"))
				server.Load(node.GetNode("server"));
		}
	}

	[KSPScenario(ScenarioCreationOptions.AddToAllGames, GameScenes.FLIGHT, GameScenes.EDITOR, GameScenes.SPACECENTER, GameScenes.TRACKSTATION)]
	public class ScenarioRIS : ScenarioModule
	{
		public static ScenarioRIS Instance {get; protected set; }
		public ConfigNode node;

		public override void OnAwake()
		{
			Instance = this;
			base.OnAwake();
		}

		public override void OnSave(ConfigNode node)
		{
			RISCore.Instance.Save(node);
		}

		public override void OnLoad(ConfigNode node)
		{
			this.node = node;
			if (RISCore.Instance != null)
				RISCore.Instance.Load(node);
		}
	}
}
